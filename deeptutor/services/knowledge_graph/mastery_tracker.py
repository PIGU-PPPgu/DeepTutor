"""Mastery tracking with exponential moving average."""

from __future__ import annotations

from dataclasses import dataclass

from deeptutor.services.knowledge_graph.graph_model import KnowledgeGraph
from deeptutor.services.knowledge_graph.graph_store import load_graph, save_graph

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
