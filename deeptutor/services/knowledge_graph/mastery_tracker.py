"""Mastery tracking with exponential moving average."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from deeptutor.services.knowledge_graph.graph_model import KnowledgeGraph
from deeptutor.services.knowledge_graph.graph_store import load_graph, save_graph

logger = logging.getLogger(__name__)

# EMA parameters
ALPHA = 0.3  # smoothing factor — higher = faster response
CORRECT_TARGET = 1.0
WRONG_TARGET = 0.0


@dataclass
class QuizResult:
    node_id: str
    correct: bool
    weight: float = 1.0  # difficulty weight


def _ema_update(current: float, correct: bool) -> float:
    """Exponential moving average toward 1.0 (correct) or 0.0 (wrong)."""
    target = CORRECT_TARGET if correct else WRONG_TARGET
    new = current + ALPHA * (target - current)
    return round(max(0.0, min(1.0, new)), 4)


def _ema_update_value(current: float, target_value: float) -> float:
    """EMA toward an arbitrary target value."""
    new = current + ALPHA * (target_value - current)
    return round(max(0.0, min(1.0, new)), 4)


def update_from_chat(node_id: str, correct: bool, kb_name: str) -> float | None:
    """Update mastery for a single node from a chat interaction. Returns new mastery or None."""
    graph = load_graph(kb_name)
    if not graph:
        return None
    node = graph.get_node(node_id)
    if not node:
        return None
    node.mastery = _ema_update(node.mastery, correct)
    save_graph(graph, kb_name)
    return node.mastery


async def update_from_chat_auto(
    kb_name: str, user_message: str, assistant_response: str
) -> None:
    """Analyze a chat turn and update mastery for relevant nodes via LLM."""
    graph = load_graph(kb_name)
    if not graph or not graph.nodes:
        return

    # Find nodes mentioned in the conversation
    mentioned_nodes: list = []
    msg_lower = (user_message + " " + assistant_response).lower()
    for node in graph.nodes:
        if node.label.lower() in msg_lower:
            mentioned_nodes.append(node)

    if not mentioned_nodes:
        return

    # Use LLM to judge understanding
    from deeptutor.services.llm import complete

    node_labels = [n.label for n in mentioned_nodes]
    prompt = (
        f"根据以下师生对话，判断学生对这些知识点的掌握程度（0.0-1.0）。\n"
        f"对每个知识点返回 JSON：{{\"知识点名\": 掌握度}}\n\n"
        f"知识点：{', '.join(node_labels)}\n\n"
        f"学生说：{user_message[:500]}\n"
        f"老师回复：{assistant_response[:500]}\n\n"
        f"只返回 JSON，不要其他文字。"
    )

    response = await complete(
        prompt, system_prompt="你是教育评估专家。只返回纯JSON。"
    )

    # Parse mastery updates
    try:
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            mastery_map = json.loads(text[start:end])
            for node in mentioned_nodes:
                if node.label in mastery_map:
                    new_mastery = float(mastery_map[node.label])
                    node.mastery = _ema_update_value(node.mastery, new_mastery)
            save_graph(graph, kb_name)
    except (json.JSONDecodeError, ValueError):
        logger.debug("Failed to parse LLM mastery response", exc_info=True)


def update_from_quiz(results: list[QuizResult], kb_name: str) -> dict[str, float]:
    """Batch update mastery from quiz results. Returns {node_id: new_mastery}."""
    graph = load_graph(kb_name)
    if not graph:
        return {}
    updated: dict[str, float] = {}
    for r in results:
        node = graph.get_node(r.node_id)
        if node:
            node.mastery = _ema_update(node.mastery, r.correct)
            updated[r.node_id] = node.mastery
    save_graph(graph, kb_name)
    return updated


def update_from_quiz_dicts(kb_name: str, results: list[dict]) -> None:
    """Update mastery from quiz results as plain dicts ({question, is_correct, topic?})."""
    graph = load_graph(kb_name)
    if not graph:
        return

    for result in results:
        question = result.get("question", "")
        is_correct = result.get("is_correct", False)
        topic = result.get("topic", "")

        # Find matching nodes
        matched = []
        if topic:
            matched = [
                n
                for n in graph.nodes
                if topic in n.label or n.label in topic
            ]
        if not matched:
            matched = [
                n
                for n in graph.nodes
                if n.label in question
                or any(kw in question for kw in n.label.split())
            ]

        for node in matched:
            node.mastery = _ema_update_value(
                node.mastery, 0.9 if is_correct else 0.1
            )

    save_graph(graph, kb_name)
