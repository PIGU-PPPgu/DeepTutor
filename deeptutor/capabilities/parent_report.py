"""Parent weekly report generation."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.services.llm import complete
from deeptutor.services.llm.config import get_llm_config

_SYSTEM_ANALYZE = """\
你是一位专业的学情分析师。根据提供的学习数据，分析学生的学习情况。

输出严格的 JSON 格式（不要包含 markdown 代码块标记）：
{
  "knowledge_heatmap": {
    "强": ["知识点A", "知识点B"],
    "中": ["知识点C"],
    "弱": ["知识点D", "知识点E"]
  },
  "trend": "进步|退步|持平",
  "trend_detail": "简要说明趋势",
  "weak_areas": ["薄弱环节1", "薄弱环节2"],
  "time_analysis": "时间投入分析说明",
  "praise_points": ["表扬点1", "表扬点2"],
  "attention_needed": ["需要关注的地方1"]
}"""

_SYSTEM_GENERATE = """\
你是一位温暖亲切的家长周报撰写专家。根据学情分析数据，撰写一份家长友好的周报。

要求：
- Markdown 格式
- 温暖积极的语气，像老师给家长写信
- 不要冷冰冰的数据堆砌
- 包含：本周概要、成绩趋势、知识点掌握、表扬点、需要关注的地方
- 附带建议活动

直接输出 Markdown 内容，不要包含代码块标记。"""

_SYSTEM_SUGGEST = """\
你是一位教育顾问。根据学情分析结果，为家长生成具体的建议。

输出严格的 JSON 格式（不要包含 markdown 代码块标记）：
{
  "parent_tips": [
    {"tip": "建议内容", "activity": "具体亲子互动活动"}
  ],
  "practice_direction": ["练习方向1", "练习方向2"],
  "next_week_focus": ["下周学习重点1", "下周学习重点2"]
}"""


def _parse_json(text: str) -> dict:
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    body = m.group(1) if m else text
    return json.loads(body.strip())


def _mock_learning_data() -> dict:
    """Generate mock learning data when no real data available."""
    return {
        "period": "本周",
        "study_days": 5,
        "total_questions": 48,
        "correct_rate": 0.78,
        "subjects": {
            "数学": {"questions": 20, "correct_rate": 0.75, "topics": ["有理数运算", "一元一次方程", "几何初步"]},
            "语文": {"questions": 15, "correct_rate": 0.87, "topics": ["古诗词默写", "阅读理解", "作文"]},
            "英语": {"questions": 13, "correct_rate": 0.69, "topics": ["词汇", "语法", "阅读"]},
        },
        "daily_minutes": [45, 60, 30, 55, 40, 0, 0],
    }


class ParentReportCapability(BaseCapability):
    manifest = CapabilityManifest(
        name="parent_report",
        description="家长端周报生成，包含学情分析和建议。",
        stages=["collect", "analyze", "generate", "suggest"],
        tools_used=[],
        cli_aliases=["parent_report", "weekly_report"],
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        config = get_llm_config()

        # Stage 1: collect
        async with stream.stage("collect", source=self.manifest.name):
            learning_data = context.metadata.get("learning_data")
            if not learning_data:
                learning_data = _mock_learning_data()

            await stream.thinking(
                "data_collected",
                {"source": "real" if context.metadata.get("learning_data") else "mock"},
                source=self.manifest.name,
            )

        # Stage 2: analyze
        async with stream.stage("analyze", source=self.manifest.name):
            analysis_raw = await complete(
                prompt=f"学习数据：\n{json.dumps(learning_data, ensure_ascii=False, indent=2)}",
                system_prompt=_SYSTEM_ANALYZE,
                model=config.model,
                api_key=config.api_key,
                base_url=config.base_url,
                temperature=0.3,
            )
            analysis = _parse_json(analysis_raw)

            await stream.thinking("analysis", source=self.manifest.name)

        # Stage 3: generate report
        async with stream.stage("generate", source=self.manifest.name):
            report_md = await complete(
                prompt=f"学情分析数据：\n{json.dumps(analysis, ensure_ascii=False, indent=2)}\n\n原始学习数据：\n{json.dumps(learning_data, ensure_ascii=False, indent=2)}",
                system_prompt=_SYSTEM_GENERATE,
                model=config.model,
                api_key=config.api_key,
                base_url=config.base_url,
                temperature=0.7,
            )

            await stream.thinking("report", source=self.manifest.name)

        # Stage 4: suggest
        async with stream.stage("suggest", source=self.manifest.name):
            suggestions_raw = await complete(
                prompt=f"学情分析：\n{json.dumps(analysis, ensure_ascii=False, indent=2)}",
                system_prompt=_SYSTEM_SUGGEST,
                model=config.model,
                api_key=config.api_key,
                base_url=config.base_url,
                temperature=0.5,
            )
            suggestions = _parse_json(suggestions_raw)

            result = {
                "report_markdown": report_md,
                "analysis": analysis,
                "suggestions": suggestions,
            }
            await stream.content(report_md, source=self.manifest.name)
