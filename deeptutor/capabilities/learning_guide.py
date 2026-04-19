"""
Learning Guide Capability
=========================

个性化学习计划生成：根据学生年级、当前进度、可用时间，生成每日学习任务。
Stages: profile → diagnose → plan → schedule

支持两种模式：
1. 对话式（通过 run 方法，LLM 多阶段生成）
2. 知识图谱驱动（通过 generate_plan 静态方法，基于掌握度数据）
"""

from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from datetime import datetime

from deeptutor.capabilities.request_contracts import get_capability_request_schema
from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus

logger = logging.getLogger(__name__)

# ---- Knowledge-graph driven plan generation ----

# Thresholds
WEAK_THRESHOLD = 0.3
TOPICS_PER_DAY = 3
MINUTES_PER_TOPIC = 25
EXERCISES_PER_TOPIC = 5


def _build_prerequisite_map(graph) -> dict[str, list[str]]:
    """Build a map: node_id -> list of prerequisite node_ids."""
    prereqs: dict[str, list[str]] = defaultdict(list)
    for edge in graph.edges:
        if edge.relation == "prerequisite":
            prereqs[edge.target_id].append(edge.source_id)
    return prereqs


def _topological_sort_weak(weak_nodes: list, graph) -> list:
    """Topologically sort weak nodes respecting prerequisite edges.

    Nodes whose prerequisites are NOT in the weak set (i.e. already mastered or
    not applicable) come first, so we always learn foundational topics first.
    """
    weak_ids = {n.id for n in weak_nodes}
    prereqs = _build_prerequisite_map(graph)

    # Build adjacency: for each weak node, which other weak nodes must come before it?
    in_degree: dict[str, int] = {n.id: 0 for n in weak_nodes}
    adj: dict[str, list[str]] = defaultdict(list)

    for n in weak_nodes:
        for pid in prereqs.get(n.id, []):
            if pid in weak_ids:
                adj[pid].append(n.id)
                in_degree[n.id] += 1

    # Kahn's algorithm
    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    # Secondary sort: lower mastery first (bigger gaps first among equal-topology nodes)
    node_map = {n.id: n for n in weak_nodes}
    queue.sort(key=lambda nid: node_map[nid].mastery)

    result: list = []
    while queue:
        nid = queue.pop(0)
        result.append(node_map[nid])
        for child in adj.get(nid, []):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)
                queue.sort(key=lambda x: node_map[x].mastery)

    # Any remaining nodes (cycles) — append as-is
    visited = {n.id for n in result}
    for n in weak_nodes:
        if n.id not in visited:
            result.append(n)

    return result


def _estimate_goal(mastery: float) -> str:
    """Generate a learning goal description based on current mastery level."""
    if mastery < 0.1:
        return "理解基本概念，能识别相关题型"
    elif mastery < 0.2:
        return "掌握核心法则，能完成基础练习"
    else:
        return "熟练运用，减少常见错误"


async def _llm_enhance_topics(topics_info: list[dict], kb_name: str) -> list[dict]:
    """Use LLM to enrich topic data with better goals and exercise suggestions."""
    from deeptutor.services.llm import complete

    prompt = (
        f"你是一位K12教育专家。以下是从「{kb_name}」知识图谱中提取的薄弱知识点：\n\n"
        f"{json.dumps(topics_info, ensure_ascii=False, indent=2)}\n\n"
        f"请为每个知识点补充：\n"
        f"1. goal: 具体的学习目标（一句话）\n"
        f"2. exercise_hint: 推荐练习类型（如：计算题、应用题、概念辨析等）\n\n"
        f"返回与输入相同格式的 JSON 列表，只补充 goal 和 exercise_hint 字段。"
    )

    try:
        response = await complete(
            prompt,
            system_prompt="你是K12教育专家，只返回纯JSON数组。",
            temperature=0.5,
        )
        text = response.strip()
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            enriched = json.loads(text[start:end])
            return enriched
    except Exception:
        logger.debug("LLM enhancement failed, using defaults", exc_info=True)
    return topics_info


async def generate_plan(kb_name: str) -> dict | None:
    """Generate a structured learning plan from knowledge graph data.

    Returns the plan dict matching the spec format, or None if graph not found.
    """
    from deeptutor.services.knowledge_graph.graph_store import load_graph

    graph = load_graph(kb_name)
    if not graph:
        return None

    weak_nodes = [n for n in graph.get_weak_nodes(WEAK_THRESHOLD) if getattr(n, "mastery", None) is not None]
    if not weak_nodes:
        # 如果没有 <0.3 的节点，取所有尚未完全掌握的有效节点
        weak_nodes = [
            n for n in graph.nodes
            if getattr(n, "mastery", None) is not None and n.mastery < 1.0
        ]
    if not weak_nodes:
        return {
            "kb_name": kb_name,
            "total_weak_points": 0,
            "estimated_days": 0,
            "daily_plans": [],
            "message": "没有发现薄弱知识点，继续保持！",
        }

    # Sort by prerequisites (foundational first)
    sorted_nodes = _topological_sort_weak(weak_nodes, graph)

    # Build topic info for LLM enrichment
    topics_info = [
        {
            "name": n.label,
            "node_id": n.id,
            "mastery": n.mastery,
            "description": n.description or "",
        }
        for n in sorted_nodes
    ]

    # LLM enrichment (best-effort)
    enriched = await _llm_enhance_topics(topics_info, kb_name)

    # Merge enriched data back
    enriched_map = {e.get("name", ""): e for e in enriched}
    for n in sorted_nodes:
        info = enriched_map.get(n.label, {})
        n._goal = info.get("goal", _estimate_goal(n.mastery))
        n._exercise_hint = info.get("exercise_hint", "基础练习")
    # Fallback for nodes not in enriched
    for n in sorted_nodes:
        if not hasattr(n, "_goal"):
            n._goal = _estimate_goal(n.mastery)
            n._exercise_hint = "基础练习"

    # Build daily plans
    total = len(sorted_nodes)
    days = math.ceil(total / TOPICS_PER_DAY)
    daily_plans = []

    for day_idx in range(days):
        start = day_idx * TOPICS_PER_DAY
        end = min(start + TOPICS_PER_DAY, total)
        day_nodes = sorted_nodes[start:end]

        topics = []
        for n in day_nodes:
            # Scale exercise count and time by mastery gap
            gap = WEAK_THRESHOLD - n.mastery
            exercises = max(3, min(8, int(EXERCISES_PER_TOPIC * (1 + gap))))
            minutes = max(15, min(40, int(MINUTES_PER_TOPIC * (1 + gap * 2))))

            topics.append({
                "name": n.label,
                "node_id": n.id,
                "mastery": round(n.mastery, 2),
                "goal": n._goal,
                "exercise_hint": n._exercise_hint,
                "exercises": exercises,
                "minutes": minutes,
            })

        daily_plans.append({
            "day": day_idx + 1,
            "topics": topics,
        })

    return {
        "kb_name": kb_name,
        "total_weak_points": total,
        "estimated_days": days,
        "daily_plans": daily_plans,
        "generated_at": datetime.now().isoformat(),
    }


# ---- In-memory plan cache (simple; production would use DB) ----

_plan_cache: dict[str, dict] = {}


def save_plan(kb_name: str, plan: dict) -> None:
    _plan_cache[kb_name] = plan


def get_cached_plan(kb_name: str) -> dict | None:
    return _plan_cache.get(kb_name)


# ---- LLM-based conversation mode (original capability) ----

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
    combined = ""
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            combined += f"{content}\n\n"
        else:
            combined += f"{content}\n"
    response = await complete(
        prompt=combined.strip(),
        system_prompt=messages[0].get("content", "") if messages and messages[0].get("role") == "system" else "You are a helpful assistant.",
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,
        api_version=config.api_version,
        temperature=0.7,
    )
    return response


def _extract_json(text: str) -> dict | list | None:
    """Try to extract JSON from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
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

            await stream.content(schedule_text, source=self.manifest.name, stage="schedule")

        await stream.result(
            {
                "student": student_profile,
                "diagnosis": diagnosis,
                "plan": plan_data,
                "schedule_markdown": schedule_text,
            },
            source=self.manifest.name,
        )
