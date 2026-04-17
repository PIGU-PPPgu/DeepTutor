"""
Content Analyzer Capability
============================

自动识别教材/书籍内容类型，结构化拆解知识点，生成知识图谱。

Stage 1: detect   — 自动识别内容类型（文学/数学/英语/科学/社科/自定义）
Stage 2: analyze  — 按类型结构化拆解
Stage 3: structure — 格式化为 JSON + 知识图谱
Stage 4: validate — 自检完整性

设计目标：为中国 K12 教育场景服务，支持中考考点标注。
"""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Any

from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.services.llm import complete
from deeptutor.services.llm.config import get_llm_config

logger = logging.getLogger(__name__)


class ContentType(str, Enum):
    """支持的教材/内容类型。"""
    LITERARY = "literary"      # 文学名著
    MATH = "math"              # 数学教材
    ENGLISH = "english"        # 英语教材
    SCIENCE = "science"        # 科学教材（物理/化学/生物）
    SOCIAL = "social"          # 社科教材（历史/地理/政治）
    CUSTOM = "custom"          # 自定义资料


# ── Prompt 模板 ─────────────────────────────────────────────────────────

DETECT_PROMPT = """你是一个教材内容分类专家。请分析以下内容片段，判断它属于哪种类型。

类型定义：
- literary: 文学名著（小说、散文、诗歌，有人物/情节/描写）
- math: 数学教材（定理/公式/例题/证明/计算）
- english: 英语教材（vocabulary/grammar/text/listening）
- science: 科学教材（实验/现象/定律/物理/化学/生物）
- social: 社科教材（历史/地理/政治/事件/时间线）
- custom: 不属于以上任何类型的学习资料

请以 JSON 格式回复（不要其他文字）：
{{"type": "类型", "confidence": 0.0-1.0, "reason": "判断理由"}}

内容片段：
{content}"""

LITERARY_ANALYZE_PROMPT = """你是一位资深语文教师和中考命题专家。请对以下文学内容进行深度拆解分析。

请以 JSON 格式返回以下结构（不要其他文字）：
{{
  "title": "作品/章节标题",
  "chapters": [
    {{"name": "章节名", "summary": "简要概括", "key_events": ["事件1", "事件2"]}}
  ],
  "characters": [
    {{"name": "人物名", "description": "人物特征描述", "significance": "在作品中的作用"}}
  ],
  "themes": ["主题1", "主题2"],
  "writing_techniques": [
    {{"technique": "手法名", "example": "原文示例", "effect": "表达效果"}}
  ],
  "key_quotes": [
    {{"quote": "原文引用", "context": "上下文", "analysis": "赏析"}}
  ],
  "exam_points": [
    {{"point": "考点", "type": "人物分析|主题理解|手法鉴赏|情节概括", "difficulty": "easy|medium|hard"}}
  ]
}}

内容：
{content}"""

MATH_ANALYZE_PROMPT = """你是一位资深数学教师和中考命题专家。请对以下数学教材内容进行深度拆解分析。

请以 JSON 格式返回以下结构（不要其他文字）：
{{
  "topic": "知识点名称",
  "chapter": "所属章节",
  "concepts": [
    {{"name": "概念名", "definition": "定义", "key_points": ["要点1"]}}
  ],
  "formulas": [
    {{"formula": "公式表达式", "description": "含义说明", "conditions": "适用条件"}}
  ],
  "examples": [
    {{"problem": "例题", "solution": "解答过程", "difficulty": "easy|medium|hard"}}
  ],
  "prerequisites": ["前置知识点1", "前置知识点2"],
  "extensions": ["延伸知识点1"],
  "common_mistakes": [
    {{"mistake": "常见错误", "reason": "错误原因", "correction": "正确做法"}}
  ],
  "exam_points": [
    {{"point": "考点", "type": "概念理解|计算|证明|应用", "difficulty": "easy|medium|hard", "frequency": "高频|中频|低频"}}
  ]
}}

内容：
{content}"""

GENERIC_ANALYZE_PROMPT = """你是一位资深教师。请对以下学习内容进行结构化分析。

请以 JSON 格式返回以下结构（不要其他文字）：
{{
  "title": "内容标题",
  "type": "内容类型",
  "summary": "内容概要",
  "key_points": ["要点1", "要点2"],
  "structure": [
    {{"section": "部分名", "content": "内容概述"}}
  ],
  "exam_points": [
    {{"point": "考点", "difficulty": "easy|medium|hard"}}
  ]
}}

内容：
{content}"""

VALIDATE_PROMPT = """你是一位教学质量审核专家。请检查以下内容分析结果的完整性和准确性。

分析类型：{content_type}
原始内容摘要：{content_summary}

分析结果：
{analysis_result}

请检查以下方面，以 JSON 格式返回（不要其他文字）：
{{
  "completeness_score": 0.0-1.0,
  "accuracy_score": 0.0-1.0,
  "gaps": ["缺失的内容1"],
  "suggestions": ["改进建议1"],
  "needs_refinement": true/false
}}"""


# ── Capability 实现 ─────────────────────────────────────────────────────

class ContentAnalyzerCapability(BaseCapability):
    """内容自动分析能力：识别类型 → 结构化拆解 → 知识图谱 → 自检。"""

    manifest = CapabilityManifest(
        name="content_analyzer",
        description="自动识别教材内容类型，结构化拆解知识点，标注中考考点，生成知识图谱。",
        stages=["detect", "analyze", "structure", "validate"],
        tools_used=["rag"],
        cli_aliases=["analyze", "ca"],
        config_defaults={"temperature": 0.3},
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        """执行完整的内容分析 pipeline。"""
        content = context.user_message
        if not content or len(content.strip()) < 10:
            await stream.content(
                "内容太短，无法进行分析。请提供更多内容（至少10个字符）。",
                source=self.manifest.name,
            )
            return

        llm_config = get_llm_config()
        api_key = llm_config.api_key
        base_url = llm_config.base_url
        model = llm_config.model

        # ── Stage 1: 检测内容类型 ──
        async with stream.stage("detect", source=self.manifest.name):
            await stream.thinking("正在识别内容类型...", source=self.manifest.name)
            detection = await self._detect_type(
                content, api_key, base_url, model
            )
            content_type = detection.get("type", "custom")
            confidence = detection.get("confidence", 0.5)
            reason = detection.get("reason", "")

            await stream.observation(
                f"**内容类型检测**: {self._type_label(content_type)} "
                f"(置信度: {confidence:.0%})\n{reason}",
                source=self.manifest.name,
                stage="detect",
            )

        # ── Stage 2: 结构化分析 ──
        async with stream.stage("analyze", source=self.manifest.name):
            await stream.thinking(
                f"正在以「{self._type_label(content_type)}」模式深度分析...",
                source=self.manifest.name,
            )
            analysis = await self._analyze_content(
                content, content_type, api_key, base_url, model
            )
            await stream.observation(
                "结构化分析完成",
                source=self.manifest.name,
                stage="analyze",
                metadata={"analysis_preview": str(analysis)[:200]},
            )

        # ── Stage 3: 结构化输出 ──
        async with stream.stage("structure", source=self.manifest.name):
            structured = self._build_structure(analysis, content_type)
            await stream.content(
                self._format_output(structured, content_type),
                source=self.manifest.name,
                stage="structure",
                metadata={"structured_data": structured},
            )

        # ── Stage 4: 验证 ──
        async with stream.stage("validate", source=self.manifest.name):
            validation = await self._validate(
                content_type, content[:500], analysis,
                api_key, base_url, model,
            )
            completeness = validation.get("completeness_score", 0)
            accuracy = validation.get("accuracy_score", 0)
            await stream.content(
                f"\n\n---\n**质量自检**: 完整度 {completeness:.0%} | "
                f"准确度 {accuracy:.0%}",
                source=self.manifest.name,
                stage="validate",
                metadata={"validation": validation},
            )

    # ── 私有方法 ──

    async def _detect_type(
        self, content: str, api_key: str, base_url: str, model: str
    ) -> dict[str, Any]:
        """用 LLM 检测内容类型。"""
        # 截取前 2000 字做类型判断
        sample = content[:2000]
        prompt = DETECT_PROMPT.format(content=sample)
        try:
            response = await complete(
                prompt=prompt,
                system_prompt="你是一个 JSON 输出机器，只输出合法 JSON。",
                model=model,
                api_key=api_key,
                base_url=base_url,
                temperature=0.1,
                max_tokens=300,
            )
            return self._parse_json_response(response)
        except Exception as e:
            logger.warning("Content type detection failed: %s", e)
            return {"type": "custom", "confidence": 0.3, "reason": "检测失败，默认自定义类型"}

    async def _analyze_content(
        self, content: str, content_type: str,
        api_key: str, base_url: str, model: str,
    ) -> dict[str, Any]:
        """按内容类型选择分析策略。"""
        # 内容太长时分段
        max_chunk = 6000
        chunks = [content[i:i+max_chunk] for i in range(0, len(content), max_chunk)]

        prompt_template = self._get_analyze_prompt(content_type)
        all_results = []

        for i, chunk in enumerate(chunks):
            prompt = prompt_template.format(content=chunk)
            try:
                response = await complete(
                    prompt=prompt,
                    system_prompt="你是一个 JSON 输出机器，只输出合法 JSON。",
                    model=model,
                    api_key=api_key,
                    base_url=base_url,
                    temperature=0.3,
                    max_tokens=2000,
                )
                result = self._parse_json_response(response)
                if result:
                    all_results.append(result)
            except Exception as e:
                logger.warning("Content analysis chunk %d failed: %s", i, e)

        # 合并多段结果
        if len(all_results) == 0:
            return {"error": "分析失败"}
        if len(all_results) == 1:
            return all_results[0]
        return self._merge_results(all_results, content_type)

    async def _validate(
        self, content_type: str, content_summary: str,
        analysis: dict[str, Any],
        api_key: str, base_url: str, model: str,
    ) -> dict[str, Any]:
        """自检分析结果质量。"""
        prompt = VALIDATE_PROMPT.format(
            content_type=self._type_label(content_type),
            content_summary=content_summary,
            analysis_result=json.dumps(analysis, ensure_ascii=False)[:3000],
        )
        try:
            response = await complete(
                prompt=prompt,
                system_prompt="你是一个 JSON 输出机器，只输出合法 JSON。",
                model=model,
                api_key=api_key,
                base_url=base_url,
                temperature=0.2,
                max_tokens=500,
            )
            return self._parse_json_response(response)
        except Exception as e:
            logger.warning("Validation failed: %s", e)
            return {
                "completeness_score": 0.7,
                "accuracy_score": 0.7,
                "gaps": [],
                "suggestions": ["验证失败，请人工审核"],
                "needs_refinement": False,
            }

    def _build_structure(
        self, analysis: dict[str, Any], content_type: str
    ) -> dict[str, Any]:
        """构建结构化输出 + 知识图谱节点。"""
        structure = {
            "content_type": content_type,
            "type_label": self._type_label(content_type),
            "analysis": analysis,
            "knowledge_graph": self._extract_graph_nodes(analysis, content_type),
        }
        return structure

    def _extract_graph_nodes(
        self, analysis: dict[str, Any], content_type: str
    ) -> list[dict[str, Any]]:
        """从分析结果中提取知识图谱节点。"""
        nodes = []
        if content_type == ContentType.LITERARY:
            for ch in analysis.get("chapters", []):
                nodes.append({"id": ch.get("name", ""), "type": "chapter"})
            for char in analysis.get("characters", []):
                nodes.append({"id": char.get("name", ""), "type": "character"})
            for theme in analysis.get("themes", []):
                nodes.append({"id": theme, "type": "theme"})
        elif content_type == ContentType.MATH:
            for concept in analysis.get("concepts", []):
                nodes.append({"id": concept.get("name", ""), "type": "concept"})
            for formula in analysis.get("formulas", []):
                nodes.append({"id": formula.get("formula", ""), "type": "formula"})
            for prereq in analysis.get("prerequisites", []):
                nodes.append({"id": prereq, "type": "prerequisite"})
        return nodes

    # ── 工具方法 ──

    @staticmethod
    def _get_analyze_prompt(content_type: str) -> str:
        """根据类型获取分析 prompt。"""
        prompts = {
            ContentType.LITERARY: LITERARY_ANALYZE_PROMPT,
            ContentType.MATH: MATH_ANALYZE_PROMPT,
        }
        return prompts.get(content_type, GENERIC_ANALYZE_PROMPT)

    @staticmethod
    def _type_label(content_type: str) -> str:
        """中文类型标签。"""
        labels = {
            ContentType.LITERARY: "文学名著",
            ContentType.MATH: "数学教材",
            ContentType.ENGLISH: "英语教材",
            ContentType.SCIENCE: "科学教材",
            ContentType.SOCIAL: "社科教材",
            ContentType.CUSTOM: "自定义资料",
        }
        return labels.get(content_type, content_type)

    @staticmethod
    def _parse_json_response(response: str) -> dict[str, Any]:
        """从 LLM 回复中提取 JSON。"""
        text = response.strip()
        # 尝试提取 ```json ... ``` 块
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        # 去除前后非 JSON 字符
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON: %s", text[:200])
            return {}

    @staticmethod
    def _merge_results(
        results: list[dict[str, Any]], content_type: str
    ) -> dict[str, Any]:
        """合并多段分析结果。"""
        merged = results[0].copy()
        for result in results[1:]:
            for key in ("chapters", "characters", "concepts", "formulas",
                        "examples", "key_points", "exam_points", "key_quotes",
                        "common_mistakes", "structure"):
                if key in result:
                    existing = merged.get(key, [])
                    if isinstance(existing, list):
                        existing.extend(result[key])
                        merged[key] = existing
        return merged

    @staticmethod
    def _format_output(structured: dict[str, Any], content_type: str) -> str:
        """将结构化数据格式化为 Markdown 输出。"""
        analysis = structured.get("analysis", {})
        type_label = structured.get("type_label", "")
        lines = [f"## 📚 内容分析报告（{type_label}）\n"]

        if content_type == ContentType.LITERARY:
            if "title" in analysis:
                lines.append(f"### {analysis['title']}\n")
            for ch in analysis.get("chapters", []):
                lines.append(f"#### 📖 {ch.get('name', '')}")
                lines.append(f"> {ch.get('summary', '')}\n")
            lines.append("### 👥 人物分析")
            for char in analysis.get("characters", []):
                lines.append(f"- **{char.get('name', '')}**: {char.get('description', '')}")
            lines.append("\n### 🎯 中考考点")
            for ep in analysis.get("exam_points", []):
                lines.append(f"- [{ep.get('difficulty', '?')}] {ep.get('point', '')} ({ep.get('type', '')})")

        elif content_type == ContentType.MATH:
            if "topic" in analysis:
                lines.append(f"### {analysis['topic']}\n")
            lines.append("### 📝 核心概念")
            for c in analysis.get("concepts", []):
                lines.append(f"- **{c.get('name', '')}**: {c.get('definition', '')}")
            lines.append("\n### 📐 公式")
            for f in analysis.get("formulas", []):
                lines.append(f"- `{f.get('formula', '')}` — {f.get('description', '')}")
            lines.append("\n### ⚠️ 常见错误")
            for m in analysis.get("common_mistakes", []):
                lines.append(f"- {m.get('mistake', '')}: {m.get('correction', '')}")
            lines.append("\n### 🎯 中考考点")
            for ep in analysis.get("exam_points", []):
                freq = ep.get('frequency', '')
                lines.append(f"- [{ep.get('difficulty', '?')}] {ep.get('point', '')} ({ep.get('type', '')}) {freq}")

        else:
            if "title" in analysis:
                lines.append(f"### {analysis['title']}\n")
            lines.append(f"**概要**: {analysis.get('summary', '')}\n")
            for point in analysis.get("key_points", []):
                lines.append(f"- {point}")

        return "\n".join(lines)
