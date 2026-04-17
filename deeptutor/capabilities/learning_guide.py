"""
Learning Guide Capability
=========================

个性化学习计划生成：根据学生年级、当前进度、可用时间，生成每日学习任务。
Stages: profile → diagnose → plan → schedule
"""

from __future__ import annotations

import json

from deeptutor.capabilities.request_contracts import get_capability_request_schema
from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus


PROFILE_SYSTEM = """\
你是一位专业的学习规划师。根据用户提供的学生信息，提取以下画像要素：
- grade: 年级（数字，如7代表初一）
- subject: 学科（math/chinese）
- current_progress: 当前进度（已学完哪些章节/知识点）
- available_time_per_day: 每天可用学习时间（分钟）
- goal: 学习目标（如"期中考试前完成第一章"）

如果信息不足，列出需要追问的问题。默认年级为7（初一）。

请以 JSON 格式输出学生画像。"""

DIAGNOSE_SYSTEM = """\
你是一位学科教育专家，熟悉《义务教育课程标准》。

根据学生画像，完成学情诊断：
1. 列出该学科对应年级的知识点序列及依赖关系
2. 基于当前进度，识别已掌握的前置知识
3. 识别薄弱环节和需要重点突破的知识点
4. 按优先级排列待学习知识点

请以结构化 JSON 输出诊断结果。"""

PLAN_SYSTEM = """\
你是一位学习计划设计师，精通布鲁姆分类法和艾宾浩斯遗忘曲线。

根据学情诊断结果，生成每日学习计划。要求：
- 每天学习时长30-45分钟
- 每个任务包含：知识点、学习目标（布鲁姆分类法层级）、学习活动、预计时长、检查点
- 学习活动类型：read（看教材）、understand（理解概念）、practice（练习）、self_test（自测）
- 按艾宾浩斯遗忘曲线安排复习日（学习后第1、2、4、7天复习）
- 重点知识标注 is_key_point: true
- 复习日标注 is_review_day: true

输出严格的 JSON 格式：
{
  "plan": {
    "total_days": 数字,
    "daily_tasks": [
      {
        "day": 1,
        "topic": "知识点名称",
        "objectives": ["目标1", "目标2"],
        "activities": [
          {"type": "read", "content": "...", "duration_min": 10},
          {"type": "practice", "content": "...", "duration_min": 15},
          {"type": "self_test", "content": "...", "duration_min": 10}
        ],
        "checkpoint": "掌握标准",
        "is_key_point": false,
        "is_review_day": false
      }
    ]
  }
}"""

SCHEDULE_SYSTEM = """\
你是一位排课助手。将学习计划转换为结构化输出。

生成两部分的输出：

1. **JSON 完整数据**：包含学生信息和完整计划
2. **Markdown 表格**：按周视图展示

Markdown 表格格式：
### 第 X 周
| 天数 | 知识点 | 活动 | 时长 | 检查点 | 备注 |
|------|--------|------|------|--------|------|

备注列标注：⭐ 重点日 / 🔄 复习日

同时生成按天视图的简要列表。"""


async def _llm_call(messages: list[dict]) -> str:
    """Call the LLM with the given messages and return the response text."""
    from deeptutor.services.llm import complete
    from deeptutor.services.llm.config import get_llm_config

    config = get_llm_config()
    response = await complete(
        messages=messages,
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,
        api_version=config.api_version,
    )
    return response


def _extract_json(text: str) -> dict | list | None:
    """Try to extract JSON from LLM output."""
    # Try direct parse first
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last ``` lines
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try to find JSON block
    start = text.find("{")
    if start == -1:
        start = text.find("[")
    if start != -1:
        for end in range(len(text), start, -1):
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                continue
    return None


class LearningGuideCapability(BaseCapability):
    manifest = CapabilityManifest(
        name="learning_guide",
        description="个性化学习计划生成：根据学生年级、进度、时间，生成每日学习任务。",
        stages=["profile", "diagnose", "plan", "schedule"],
        tools_used=["rag"],
        cli_aliases=["learning-guide", "guide"],
        request_schema=get_capability_request_schema("learning_guide"),
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        user_message = context.user_message

        # ---- Stage 1: Profile ----
        async with stream.stage("profile", source=self.manifest.name):
            await stream.thinking("📋 正在分析学生信息...\n", source=self.manifest.name, stage="profile")

            profile_messages = [
                {"role": "system", "content": PROFILE_SYSTEM},
                {"role": "user", "content": user_message or "请为七年级学生制定学习计划"},
            ]
            profile_text = await _llm_call(profile_messages)
            await stream.observation(profile_text, source=self.manifest.name, stage="profile")

            student_profile = _extract_json(profile_text)
            if student_profile is None:
                student_profile = {"grade": 7, "subject": "math", "current_progress": "", "available_time_per_day": 40, "goal": ""}
                await stream.content(
                    "未能完全解析学生信息，将使用默认设置（七年级数学，每天40分钟）继续。\n\n",
                    source=self.manifest.name,
                    stage="profile",
                )

        # ---- Stage 2: Diagnose ----
        async with stream.stage("diagnose", source=self.manifest.name):
            await stream.thinking("🔍 正在进行学情诊断...\n", source=self.manifest.name, stage="diagnose")

            diagnose_messages = [
                {"role": "system", "content": DIAGNOSE_SYSTEM},
                {"role": "user", "content": f"学生画像：{json.dumps(student_profile, ensure_ascii=False)}"},
            ]
            diagnose_text = await _llm_call(diagnose_messages)
            await stream.observation(diagnose_text, source=self.manifest.name, stage="diagnose")

            diagnosis = _extract_json(diagnose_text) or {}

        # ---- Stage 3: Plan ----
        async with stream.stage("plan", source=self.manifest.name):
            await stream.thinking("📝 正在生成学习计划...\n", source=self.manifest.name, stage="plan")

            plan_messages = [
                {"role": "system", "content": PLAN_SYSTEM},
                {"role": "user", "content": (
                    f"学生画像：{json.dumps(student_profile, ensure_ascii=False)}\n\n"
                    f"学情诊断：{json.dumps(diagnosis, ensure_ascii=False)}"
                )},
            ]
            plan_text = await _llm_call(plan_messages)
            await stream.observation(plan_text, source=self.manifest.name, stage="plan")

            plan_data = _extract_json(plan_text) or {"total_days": 0, "daily_tasks": []}

        # ---- Stage 4: Schedule ----
        async with stream.stage("schedule", source=self.manifest.name):
            await stream.thinking("📅 正在生成排课表...\n", source=self.manifest.name, stage="schedule")

            schedule_messages = [
                {"role": "system", "content": SCHEDULE_SYSTEM},
                {"role": "user", "content": (
                    f"学生画像：{json.dumps(student_profile, ensure_ascii=False)}\n\n"
                    f"学习计划：{json.dumps(plan_data, ensure_ascii=False)}"
                )},
            ]
            schedule_text = await _llm_call(schedule_messages)

            # Output the final schedule as content
            await stream.content(schedule_text, source=self.manifest.name, stage="schedule")

        # Emit structured result
        await stream.result(
            {
                "student": student_profile,
                "diagnosis": diagnosis,
                "plan": plan_data,
                "schedule_markdown": schedule_text,
            },
            source=self.manifest.name,
        )
