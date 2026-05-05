"""Parent weekly report generation.

Generates warm, teacher-like reports for parents of K12 students,
based on knowledge graph mastery data.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta

from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.services.knowledge_graph.graph_store import load_graph
from deeptutor.services.knowledge_graph.graph_model import KnowledgeGraph, KnowledgeNode
from deeptutor.services.llm import complete
from deeptutor.services.llm.config import get_llm_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_WEEKLY = """\
你是一位温暖专业的班主任老师，正在给学生家长写一份学习周报。

你的语气像和家长面对面聊天——既不冷冰冰堆数据，也不泛泛而谈。
会具体指出进步的地方（带着真诚的表扬），也会温和地提醒需要关注的问题。

根据提供的学习数据，直接输出 Markdown 格式的周报，包含以下部分：

# 📊 学习周报 — {subject}（{date_range}）

## 📈 总体进度
- 列出知识点统计：已掌握/学习中/薄弱
- 总体掌握度百分比

## 🎯 各模块表现
- 用表格展示每个模块（章节）的掌握度和趋势箭头

## ⚠️ 需要关注
- 列出掌握度最低的知识点，每个给出简短提醒

## 💡 家长辅导建议
- 3-5条具体可操作的建议，不要太抽象

## 💬 讨论话题
- 3-5个家长可以和孩子聊天讨论的话题，帮助孩子巩固

注意：
- 语气温暖、鼓励为主，但问题也要说清楚
- 使用中国初中教育的常见术语
- 直接输出 Markdown，不要包含代码块标记"""

_SYSTEM_PROGRESS = """\
你是一位教育数据分析师。根据知识图谱数据，生成掌握度分析报告。

直接输出 Markdown 格式，包含：
1. 各章节掌握度表格
2. 薄弱知识点清单
3. 学习路径建议（应该先补什么再学什么）

语气专业但不冰冷。直接输出 Markdown。"""

_SYSTEM_SUGGEST = """\
你是一位经验丰富的家庭教育顾问。根据学生的学习薄弱点，给家长提供具体的辅导建议。

输出严格的 JSON 格式（不要包含 markdown 代码块标记）：
{
  "parent_tips": [
    {"tip": "建议内容", "activity": "具体亲子互动活动"}
  ],
  "discussion_topics": [
    "讨论话题1",
    "讨论话题2"
  ],
  "practice_direction": ["练习方向1"],
  "next_week_focus": ["下周重点1"]
}"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json(text: str) -> dict:
    """Extract JSON from LLM output (handles code blocks)."""
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    body = m.group(1) if m else text
    return json.loads(body.strip())


def _pct(v: float) -> str:
    return f"{int(round(v * 100))}%"


def _trend_arrow(current: float, previous: float | None) -> str:
    if previous is None:
        return "→"
    diff = current - previous
    if diff > 0.05:
        return "↑"
    elif diff < -0.05:
        return "↓"
    return "→"


def _node_level_name(level: int) -> str:
    return {0: "学科", 1: "章节", 2: "知识点", 3: "考点"}.get(level, f"L{level}")


# ---------------------------------------------------------------------------
# Data extraction from KnowledgeGraph
# ---------------------------------------------------------------------------

def _extract_modules(graph: KnowledgeGraph) -> list[dict]:
    """Group nodes by chapter (level=1) and compute stats."""
    chapters: dict[str, list[KnowledgeNode]] = defaultdict(list)
    orphans: list[KnowledgeNode] = []

    for node in graph.nodes:
        if node.level == 1:
            chapters[node.id].append(node)
        elif node.level >= 2 and node.parent_id:
            chapters[node.parent_id].append(node)
        elif node.level >= 2:
            orphans.append(node)

    # Also include level-1 nodes themselves in their group
    result = []
    for node in graph.nodes:
        if node.level == 1:
            children = chapters.get(node.id, [])
            # The chapter node itself may have mastery=0 if never directly assessed
            all_nodes = [node] + children
            mastery_values = [n.mastery for n in all_nodes if n.mastery > 0]
            avg = sum(mastery_values) / len(mastery_values) if mastery_values else 0.0
            result.append({
                "name": node.label,
                "mastery": avg,
                "total": len(all_nodes),
                "mastered": sum(1 for n in all_nodes if n.mastery >= 0.8),
                "learning": sum(1 for n in all_nodes if 0.3 <= n.mastery < 0.8),
                "weak": sum(1 for n in all_nodes if 0 < n.mastery < 0.3),
                "unstudied": sum(1 for n in all_nodes if n.mastery == 0),
            })

    # Handle orphan knowledge points (no chapter parent)
    if orphans:
        mastery_values = [n.mastery for n in orphans if n.mastery > 0]
        avg = sum(mastery_values) / len(mastery_values) if mastery_values else 0.0
        result.append({
            "name": "其他知识点",
            "mastery": avg,
            "total": len(orphans),
            "mastered": sum(1 for n in orphans if n.mastery >= 0.8),
            "learning": sum(1 for n in orphans if 0.3 <= n.mastery < 0.8),
            "weak": sum(1 for n in orphans if 0 < n.mastery < 0.3),
            "unstudied": sum(1 for n in orphans if n.mastery == 0),
        })

    result.sort(key=lambda m: m["mastery"])
    return result


def _extract_weak_points(graph: KnowledgeGraph, threshold: float = 0.3) -> list[dict]:
    """Get weak knowledge points with parent context."""
    weak = graph.get_weak_nodes(threshold)
    result = []
    for node in weak:
        parent = graph.get_node(node.parent_id) if node.parent_id else None
        result.append({
            "label": node.label,
            "mastery": node.mastery,
            "chapter": parent.label if parent else "未分类",
            "level": _node_level_name(node.level),
        })
    result.sort(key=lambda x: x["mastery"])
    return result


def _build_data_summary(graph: KnowledgeGraph, kb_name: str) -> dict:
    """Build a summary dict from graph for LLM consumption."""
    stats = graph.stats()
    modules = _extract_modules(graph)
    weak_points = _extract_weak_points(graph)

    # Find prerequisites for weak nodes
    prerequisite_hints = []
    weak_ids = {n["label"] for n in weak_points}
    for edge in graph.edges:
        if edge.relation == "prerequisite":
            target = graph.get_node(edge.target_id)
            source = graph.get_node(edge.source_id)
            if target and source and target.label in weak_ids:
                prerequisite_hints.append(f"{source.label} → {target.label}")

    return {
        "kb_name": kb_name,
        "stats": stats,
        "modules": modules,
        "weak_points": weak_points,
        "prerequisite_hints": prerequisite_hints[:10],
    }


# ---------------------------------------------------------------------------
# Report generation functions (can be called independently or via capability)
# ---------------------------------------------------------------------------

async def generate_weekly_report(kb_name: str) -> str:
    """Generate a full weekly report as Markdown."""
    graph = load_graph(kb_name)
    if not graph:
        return f"⚠️ 未找到知识图谱「{kb_name}」，请先创建知识图谱。"

    data = _build_data_summary(graph, kb_name)

    # Determine subject name from level-0 node or kb_name
    subject_node = next((n for n in graph.nodes if n.level == 0), None)
    subject = subject_node.label if subject_node else kb_name

    now = datetime.now()
    week_ago = now - timedelta(days=7)
    date_range = f"{week_ago.month}月{week_ago.day}日-{now.month}月{now.day}日"

    config = get_llm_config()
    system = _SYSTEM_WEEKLY.format(subject=subject, date_range=date_range)

    report = await complete(
        prompt=f"学习数据：\n{json.dumps(data, ensure_ascii=False, indent=2)}",
        system_prompt=system,
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,
        temperature=0.7,
    )

    return report.strip()


async def generate_progress_report(kb_name: str) -> str:
    """Generate a progress/mastery report as Markdown."""
    graph = load_graph(kb_name)
    if not graph:
        return f"⚠️ 未找到知识图谱「{kb_name}」，请先创建知识图谱。"

    data = _build_data_summary(graph, kb_name)
    config = get_llm_config()

    report = await complete(
        prompt=f"知识图谱掌握度数据：\n{json.dumps(data, ensure_ascii=False, indent=2)}",
        system_prompt=_SYSTEM_PROGRESS,
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,
        temperature=0.5,
    )

    return report.strip()


async def generate_suggestions(kb_name: str) -> dict:
    """Generate parent suggestions as structured data."""
    graph = load_graph(kb_name)
    if not graph:
        return {"error": f"未找到知识图谱「{kb_name}」"}

    data = _build_data_summary(graph, kb_name)
    config = get_llm_config()

    raw = await complete(
        prompt=f"学情数据：\n{json.dumps(data, ensure_ascii=False, indent=2)}",
        system_prompt=_SYSTEM_SUGGEST,
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,
        temperature=0.5,
    )

    try:
        return _parse_json(raw)
    except json.JSONDecodeError:
        return {"raw_text": raw}


# ---------------------------------------------------------------------------
# Capability class (BaseCapability interface)
# ---------------------------------------------------------------------------

class ParentReportCapability(BaseCapability):
    manifest = CapabilityManifest(
        name="parent_report",
        description="家长端周报生成，包含学情分析和建议。",
        stages=["collect", "analyze", "generate", "suggest"],
        tools_used=[],
        cli_aliases=["parent_report", "weekly_report"],
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        kb_name = context.metadata.get("kb_name", "default")

        # Stage 1: collect
        async with stream.stage("collect", source=self.manifest.name):
            graph = load_graph(kb_name)
            if not graph:
                await stream.content(
                    f"⚠️ 未找到知识图谱「{kb_name}」，请先创建知识图谱。",
                    source=self.manifest.name,
                )
                return

            data = _build_data_summary(graph, kb_name)
            await stream.thinking(
                "data_collected",
                {"kb_name": kb_name, "stats": data["stats"]},
                source=self.manifest.name,
            )

        # Stage 2: analyze
        async with stream.stage("analyze", source=self.manifest.name):
            await stream.thinking("analysis", source=self.manifest.name)

        # Stage 3: generate report
        async with stream.stage("generate", source=self.manifest.name):
            report_md = await generate_weekly_report(kb_name)
            await stream.thinking("report", source=self.manifest.name)

        # Stage 4: suggest
        async with stream.stage("suggest", source=self.manifest.name):
            suggestions = await generate_suggestions(kb_name)

            await stream.content(report_md, source=self.manifest.name)
