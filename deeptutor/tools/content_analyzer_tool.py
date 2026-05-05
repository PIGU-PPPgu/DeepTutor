"""
Content Analyzer Tool
=====================

Tool 版本的 content_analyzer，可在普通 chat 模式下通过 function-calling 调用。
底层复用 ContentAnalyzerCapability 的核心分析逻辑。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from deeptutor.core.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult

logger = logging.getLogger(__name__)


class ContentAnalyzerTool(BaseTool):
    """内容分析工具：自动识别教材内容类型，结构化拆解知识点。"""

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="content_analyzer",
            description=(
                "分析教材/书籍内容，自动识别类型（文学/数学/英语/科学/社科），"
                "结构化拆解知识点，标注中考考点，生成知识图谱。"
                "适用于：课文分析、知识点梳理、考点提取。"
            ),
            parameters=[
                ToolParameter(
                    name="content",
                    type="string",
                    description="要分析的教材/书籍内容文本。",
                ),
                ToolParameter(
                    name="content_type",
                    type="string",
                    description=(
                        "强制指定内容类型，可选：literary, math, english, science, social, custom。"
                        "留空则自动检测。"
                    ),
                    required=False,
                    default="",
                    enum=["literary", "math", "english", "science", "social", "custom", ""],
                ),
            ],
        )

    @property
    def name(self) -> str:
        return "content_analyzer"

    async def execute(self, **kwargs: Any) -> ToolResult:
        from deeptutor.capabilities.content_analyzer import ContentAnalyzerCapability
        from deeptutor.services.llm.config import get_llm_config

        content = kwargs.get("content", "")
        forced_type = kwargs.get("content_type", "")

        if not content or len(content.strip()) < 10:
            return ToolResult(
                content="内容太短，无法进行分析。请提供更多内容（至少10个字符）。",
                success=False,
            )

        cap = ContentAnalyzerCapability()
        llm_config = get_llm_config()
        api_key = llm_config.api_key
        base_url = llm_config.base_url
        model = llm_config.model

        # Detect or use forced type
        if forced_type:
            content_type = forced_type
            confidence = 1.0
        else:
            detection = await cap._detect_type(content, api_key, base_url, model)
            content_type = detection.get("type", "custom")
            confidence = detection.get("confidence", 0.5)

        # Analyze
        analysis = await cap._analyze_content(
            content, content_type, api_key, base_url, model
        )

        # Build structured output
        structured = cap._build_structure(analysis, content_type)
        formatted = cap._format_output(structured, content_type)

        # Add metadata
        meta = {
            "content_type": content_type,
            "type_label": cap._type_label(content_type),
            "confidence": confidence,
            "forced_type": bool(forced_type),
            "analysis": analysis,
            "knowledge_graph": structured.get("knowledge_graph", []),
        }

        return ToolResult(
            content=formatted,
            success=True,
            metadata=meta,
        )
