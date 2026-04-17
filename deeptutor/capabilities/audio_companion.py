"""
Audio Companion Capability
============================

NotebookLM 式播客生成：上传内容 → 一键生成5-10分钟双人对话播客脚本 + TTS音频。

Stages: script → enhance → tts → assemble

设计目标：为中国初中生服务，生成自然有趣的双人对话播客。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.services.llm import complete
from deeptutor.services.llm.config import get_llm_config

logger = logging.getLogger(__name__)

# ── Prompt 模板 ─────────────────────────────────────────────────────────

SCRIPT_PROMPT = """你是一位资深播客脚本作家，擅长把知识内容变成轻松有趣的双人对话。

请根据以下学习内容，生成一段5-10分钟的双人对话播客脚本（约2000-3000字中文）。

要求：
- 两个角色：老师（引导讲解，专业但亲切）和学生（好奇提问，代表听众视角）
- 风格：像朋友聊天，不要像课堂讲座
- 知识点要自然地穿插在对话中
- 适合初中生理解
- 对话要有节奏感，有起承转合

输出格式（每行一段对话，用以下格式）：
老师：xxx
学生：xxx

学习内容：
{content}"""

ENHANCE_PROMPT = """你是一位播客制作专家。请优化以下双人对话脚本，让它听起来更自然、更有播客感。

要求：
1. 适当添加语气词（"嗯"、"对对对"、"原来如此"、"哇"、"等等"等）
2. 在自然停顿处添加标记：[停顿1秒]、[停顿2秒]、[停顿3秒]
3. 在关键知识点处添加强调标记：**重点内容**
4. 保持对话流畅，不要过度添加语气词
5. 确保知识点准确无误
6. 保持原有格式：老师/学生 + 冒号 + 内容

优化后的脚本：
{script}"""

# ── TTS 配置 ────────────────────────────────────────────────────────────

TTS_API_URL = "https://api.siliconflow.cn/v1/audio/speech"
TTS_MODEL = "siliconflow-tts-001"
# 男声（老师）和女声（学生）
VOICE_TEACHER = "alex"    # 男声
VOICE_STUDENT = "beth"    # 女声


# ── Capability 实现 ─────────────────────────────────────────────────────

class AudioCompanionCapability(BaseCapability):
    """播客式学习内容生成：脚本 → 增强 → TTS → 组装。"""

    manifest = CapabilityManifest(
        name="audio_companion",
        description="NotebookLM 式播客生成：将学习内容转化为5-10分钟双人对话播客脚本+TTS音频。",
        stages=["script", "enhance", "tts", "assemble"],
        tools_used=[],
        cli_aliases=["podcast", "audio"],
        config_defaults={"temperature": 0.7},
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        content = context.user_message
        if not content or len(content.strip()) < 20:
            await stream.content(
                "内容太短，无法生成播客。请提供更多学习内容（至少20个字符）。",
                source=self.manifest.name,
            )
            return

        llm_config = get_llm_config()
        api_key = llm_config.api_key
        base_url = llm_config.base_url
        model = llm_config.model

        # ── Stage 1: 生成对话脚本 ──
        async with stream.stage("script", source=self.manifest.name):
            await stream.thinking("正在生成双人对话脚本...", source=self.manifest.name)
            raw_script = await self._generate_script(
                content, api_key, base_url, model
            )
            await stream.observation(
                f"对话脚本已生成（约{len(raw_script)}字）",
                source=self.manifest.name,
                stage="script",
            )

        # ── Stage 2: 增强脚本 ──
        async with stream.stage("enhance", source=self.manifest.name):
            await stream.thinking("正在优化脚本，添加语气词和停顿...", source=self.manifest.name)
            enhanced = await self._enhance_script(
                raw_script, api_key, base_url, model
            )
            await stream.observation(
                "脚本增强完成",
                source=self.manifest.name,
                stage="enhance",
            )

        # ── Stage 3: TTS ──
        audio_segments: list[dict[str, Any]] = []
        async with stream.stage("tts", source=self.manifest.name):
            await stream.thinking("正在生成语音...", source=self.manifest.name)
            audio_segments = await self._tts_generate(enhanced, api_key)
            if audio_segments:
                await stream.observation(
                    f"已生成 {len(audio_segments)} 段语音",
                    source=self.manifest.name,
                    stage="tts",
                )
            else:
                await stream.observation(
                    "TTS 暂不可用，将只返回脚本",
                    source=self.manifest.name,
                    stage="tts",
                )

        # ── Stage 4: 组装输出 ──
        async with stream.stage("assemble", source=self.manifest.name):
            output = self._assemble(enhanced, audio_segments)
            await stream.content(
                output,
                source=self.manifest.name,
                stage="assemble",
            )

    # ── 私有方法 ──

    async def _generate_script(
        self, content: str, api_key: str, base_url: str, model: str
    ) -> str:
        prompt = SCRIPT_PROMPT.format(content=content[:6000])
        response = await complete(
            prompt=prompt,
            system_prompt="你是一位播客脚本作家。只输出对话脚本，不要其他内容。",
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=0.7,
            max_tokens=4000,
        )
        return response.strip()

    async def _enhance_script(
        self, script: str, api_key: str, base_url: str, model: str
    ) -> str:
        prompt = ENHANCE_PROMPT.format(script=script)
        response = await complete(
            prompt=prompt,
            system_prompt="你是一位播客制作专家。只输出优化后的脚本，保持原有格式。",
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=0.5,
            max_tokens=4000,
        )
        return response.strip()

    async def _tts_generate(
        self, script: str, api_key: str
    ) -> list[dict[str, Any]]:
        """按角色分段生成 TTS 音频。"""
        segments: list[dict[str, Any]] = []
        lines = self._parse_dialogue(script)
        if not lines:
            return segments

        async with httpx.AsyncClient(timeout=30) as client:
            for role, text in lines:
                voice = VOICE_TEACHER if "老师" in role else VOICE_STUDENT
                # 去掉停顿标记
                clean_text = re.sub(r'\[停顿\d+秒\]', '', text).strip()
                if not clean_text:
                    continue
                try:
                    resp = await client.post(
                        TTS_API_URL,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": TTS_MODEL,
                            "input": clean_text,
                            "voice": voice,
                        },
                    )
                    if resp.status_code == 200:
                        segments.append({
                            "role": role,
                            "text": clean_text,
                            "audio_size": len(resp.content),
                        })
                    else:
                        logger.warning(
                            "TTS failed for %s: %d %s",
                            role, resp.status_code, resp.text[:200],
                        )
                except Exception as e:
                    logger.warning("TTS error: %s", e)

        return segments

    def _assemble(
        self, enhanced_script: str, audio_segments: list[dict[str, Any]]
    ) -> str:
        """组装最终 Markdown 输出。"""
        lines = ["## 🎙️ 学习播客脚本\n"]
        lines.append(enhanced_script)

        if audio_segments:
            lines.append("\n\n---\n### 🔊 音频信息")
            lines.append(f"- 共生成 {len(audio_segments)} 段语音")
            teacher_count = sum(1 for s in audio_segments if "老师" in s["role"])
            student_count = len(audio_segments) - teacher_count
            lines.append(f"- 老师语音：{teacher_count} 段 | 学生语音：{student_count} 段")
            total_size = sum(s["audio_size"] for s in audio_segments)
            lines.append(f"- 音频总大小：{total_size / 1024:.0f} KB")

        return "\n".join(lines)

    @staticmethod
    def _parse_dialogue(script: str) -> list[tuple[str, str]]:
        """解析对话脚本为 (角色, 内容) 列表。"""
        lines = []
        for line in script.split("\n"):
            line = line.strip()
            if not line:
                continue
            match = re.match(r'^(老师|学生)[：:]\s*(.*)', line)
            if match:
                lines.append((match.group(1), match.group(2)))
        return lines
