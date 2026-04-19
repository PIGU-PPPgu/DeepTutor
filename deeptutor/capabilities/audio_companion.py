"""
Audio Companion Capability
============================

NotebookLM 式播客生成：上传内容 → 一键生成5-10分钟双人对话播客脚本 + TTS音频。

Stages: script → enhance → tts → assemble

设计目标：为中国初中生服务，生成自然有趣的双人对话播客。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import struct
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

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

# 硅基流动 TTS 配置（主力）
SILICONFLOW_TTS_API_URL = "https://api.siliconflow.cn/v1/audio/speech"
SILICONFLOW_TTS_MODEL = "siliconflow-tts-001"
SILICONFLOW_API_KEY = os.environ.get(
    "SILICONFLOW_API_KEY",
    "",  # 必须通过环境变量设置
)

# 角色声音映射
VOICE_TEACHER = "alex"   # 成熟男声
VOICE_STUDENT = "beth"   # 年轻女声

# Edge TTS voices（备用）
EDGE_VOICE_TEACHER = "zh-CN-YunxiNeural"
EDGE_VOICE_STUDENT = "zh-CN-XiaoxiaoNeural"

# 音频输出目录
AUDIO_OUTPUT_DIR = Path("data/user/workspace/audio")


# ── 播客任务管理 ────────────────────────────────────────────────────────

class PodcastTask:
    """跟踪播客生成任务的状态。"""

    def __init__(self, task_id: str, kb_name: str, title: str = ""):
        self.task_id = task_id
        self.kb_name = kb_name
        self.title = title
        self.status = "pending"  # pending → generating → completed / failed
        self.progress = 0.0  # 0.0 ~ 1.0
        self.script: str = ""
        self.enhanced_script: str = ""
        self.output_path: Optional[Path] = None
        self.error: Optional[str] = None
        self.created_at = datetime.now()
        self.dialogue: list[dict[str, str]] = []

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "kb_name": self.kb_name,
            "title": self.title,
            "status": self.status,
            "progress": self.progress,
            "output_path": str(self.output_path) if self.output_path else None,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "dialogue_count": len(self.dialogue),
        }


# 全局任务存储
_podcast_tasks: dict[str, PodcastTask] = {}


def get_podcast_task(task_id: str) -> Optional[PodcastTask]:
    return _podcast_tasks.get(task_id)


def list_podcast_tasks(kb_name: Optional[str] = None) -> list[PodcastTask]:
    tasks = list(_podcast_tasks.values())
    if kb_name:
        tasks = [t for t in tasks if t.kb_name == kb_name]
    return sorted(tasks, key=lambda t: t.created_at, reverse=True)


# ── 音频拼接工具 ────────────────────────────────────────────────────────

def concat_mp3(files: list[Path], output: Path) -> None:
    """
    简单拼接 MP3 文件。
    因为 MP3 由独立帧组成，直接二进制拼接后大多数播放器都能正常播放。
    """
    with open(output, "wb") as out:
        for f in files:
            if f.exists():
                out.write(f.read_bytes())


def get_audio_duration_mp3(path: Path) -> float:
    """粗略估算 MP3 时长（秒）。"""
    try:
        size = path.stat().st_size
        # MP3 128kbps ≈ 16KB/s
        return size / 16000.0
    except Exception:
        return 0.0


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

        # ── Stage 1: 生成对话脚本 ──
        async with stream.stage("script", source=self.manifest.name):
            await stream.thinking("正在生成双人对话脚本...", source=self.manifest.name)
            raw_script = await self._generate_script(content, llm_config)
            await stream.observation(
                f"对话脚本已生成（约{len(raw_script)}字）",
                source=self.manifest.name,
                stage="script",
            )

        # ── Stage 2: 增强脚本 ──
        async with stream.stage("enhance", source=self.manifest.name):
            await stream.thinking("正在优化脚本，添加语气词和停顿...", source=self.manifest.name)
            enhanced = await self._enhance_script(raw_script, llm_config)
            await stream.observation(
                "脚本增强完成",
                source=self.manifest.name,
                stage="enhance",
            )

        # ── Stage 3: TTS ──
        audio_segments: list[dict[str, Any]] = []
        async with stream.stage("tts", source=self.manifest.name):
            await stream.thinking("正在生成语音...", source=self.manifest.name)
            audio_segments = await self._tts_generate(enhanced)
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

    # ── 公开 API：播客生成（后台任务） ──

    async def generate_podcast(
        self,
        kb_name: str,
        content: str,
        title: str = "",
    ) -> PodcastTask:
        """
        生成完整播客（异步后台任务）。
        返回 PodcastTask 用于跟踪状态。
        """
        task_id = uuid.uuid4().hex[:12]
        task = PodcastTask(task_id=task_id, kb_name=kb_name, title=title)
        _podcast_tasks[task_id] = task

        # 在后台执行生成
        asyncio.create_task(
            self._run_podcast_pipeline(task, content)
        )
        return task

    async def _run_podcast_pipeline(
        self, task: PodcastTask, content: str
    ) -> None:
        """执行完整播客生成流水线。"""
        try:
            task.status = "generating"
            llm_config = get_llm_config()

            # Step 1: 生成脚本
            task.progress = 0.1
            raw_script = await self._generate_script(content, llm_config)
            task.script = raw_script

            # Step 2: 增强脚本
            task.progress = 0.3
            enhanced = await self._enhance_script(raw_script, llm_config)
            task.enhanced_script = enhanced

            # 解析对话为结构化格式
            task.dialogue = self._parse_dialogue_to_dicts(enhanced)

            # 从脚本中提取标题
            if not task.title:
                task.title = self._extract_title(raw_script) or f"{kb_name} 学习播客"

            # Step 3: TTS 生成音频
            task.progress = 0.5
            lines = self._parse_dialogue(enhanced)
            audio_dir = AUDIO_OUTPUT_DIR / task.task_id
            audio_dir.mkdir(parents=True, exist_ok=True)

            segment_files: list[Path] = []
            total = len(lines)
            for idx, (role, text) in enumerate(lines):
                task.progress = 0.5 + 0.4 * (idx / max(total, 1))
                audio_bytes = await self._tts_single(role, text)
                if audio_bytes:
                    seg_path = audio_dir / f"seg_{idx:04d}.mp3"
                    seg_path.write_bytes(audio_bytes)
                    segment_files.append(seg_path)

            # Step 4: 拼接音频
            task.progress = 0.95
            if segment_files:
                output_path = AUDIO_OUTPUT_DIR / f"podcast_{task.task_id}.mp3"
                concat_mp3(segment_files, output_path)
                task.output_path = output_path
                duration = get_audio_duration_mp3(output_path)
                logger.info(
                    "Podcast %s assembled: %d segments, %.1f min",
                    task.task_id, len(segment_files), duration / 60,
                )

            task.progress = 1.0
            task.status = "completed"

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            logger.exception("Podcast generation failed for task %s", task.task_id)

    # ── 私有方法 ──

    async def _generate_script(self, content: str, llm_config) -> str:
        prompt = SCRIPT_PROMPT.format(content=content[:6000])
        response = await complete(
            prompt=prompt,
            system_prompt="你是一位播客脚本作家。只输出对话脚本，不要其他内容。",
            model=llm_config.model,
            api_key=llm_config.api_key,
            base_url=llm_config.base_url,
            temperature=0.7,
            max_tokens=4000,
        )
        return response.strip()

    async def _enhance_script(self, script: str, llm_config) -> str:
        prompt = ENHANCE_PROMPT.format(script=script)
        response = await complete(
            prompt=prompt,
            system_prompt="你是一位播客制作专家。只输出优化后的脚本，保持原有格式。",
            model=llm_config.model,
            api_key=llm_config.api_key,
            base_url=llm_config.base_url,
            temperature=0.5,
            max_tokens=4000,
        )
        return response.strip()

    async def _tts_generate(self, script: str) -> list[dict[str, Any]]:
        """按角色分段生成 TTS 音频。"""
        lines = self._parse_dialogue(script)
        if not lines:
            return []

        segments: list[dict[str, Any]] = []
        for role, text in lines:
            audio_bytes = await self._tts_single(role, text)
            if audio_bytes:
                segments.append({
                    "role": role,
                    "text": re.sub(r'\[停顿\d+秒\]', '', text).strip(),
                    "audio_size": len(audio_bytes),
                })

        return segments

    async def _tts_single(self, role: str, text: str) -> Optional[bytes]:
        """为单句台词生成 TTS 音频。优先硅基流动，失败则 fallback 到 Edge TTS。"""
        clean_text = re.sub(r'\[停顿\d+秒\]', '', text).strip()
        if not clean_text:
            return None

        # 硅基流动 TTS（主力）
        result = await self._siliconflow_tts(role, clean_text)
        if result:
            return result

        # Edge TTS（备用）
        logger.warning("SiliconFlow TTS failed, trying Edge TTS for: %s", role)
        return await self._edge_tts(role, clean_text)

    async def _siliconflow_tts(self, role: str, text: str) -> Optional[bytes]:
        """硅基流动 TTS API 调用。"""
        voice = VOICE_TEACHER if "老师" in role else VOICE_STUDENT
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    SILICONFLOW_TTS_API_URL,
                    headers={
                        "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": SILICONFLOW_TTS_MODEL,
                        "input": text,
                        "voice": voice,
                        "response_format": "mp3",
                    },
                )
                if resp.status_code == 200:
                    return resp.content
                else:
                    logger.warning(
                        "SiliconFlow TTS failed: %d %s",
                        resp.status_code, resp.text[:200],
                    )
        except Exception as e:
            logger.warning("SiliconFlow TTS error: %s", e)
        return None

    async def _edge_tts(self, role: str, text: str) -> Optional[bytes]:
        """Edge TTS（备用方案）。"""
        try:
            import edge_tts
            import io
        except ImportError:
            logger.warning("edge-tts not installed, run: pip install edge-tts")
            return None

        voice = EDGE_VOICE_TEACHER if "老师" in role else EDGE_VOICE_STUDENT
        try:
            communicate = edge_tts.Communicate(text, voice)
            buffer = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buffer.write(chunk["data"])
            audio_bytes = buffer.getvalue()
            return audio_bytes if audio_bytes else None
        except Exception as e:
            logger.warning("Edge TTS error: %s", e)
            return None

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

    @staticmethod
    def _parse_dialogue_to_dicts(script: str) -> list[dict[str, str]]:
        """解析对话脚本为结构化字典列表。"""
        result = []
        for line in script.split("\n"):
            line = line.strip()
            if not line:
                continue
            match = re.match(r'^(老师|学生)[：:]\s*(.*)', line)
            if match:
                result.append({"speaker": match.group(1), "text": match.group(2)})
        return result

    @staticmethod
    def _extract_title(script: str) -> str:
        """从脚本中提取标题（取第一行有内容的）。"""
        for line in script.split("\n"):
            line = line.strip()
            if line and not line.startswith("老师") and not line.startswith("学生"):
                return line[:50]
        return ""
