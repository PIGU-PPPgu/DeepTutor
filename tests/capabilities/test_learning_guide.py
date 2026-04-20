"""Unit tests for learning_guide capability — pure logic only, no LLM calls."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from deeptutor.capabilities.learning_guide import (
    WEAK_THRESHOLD,
    _topological_sort_weak,
    generate_plan,
)
from deeptutor.services.knowledge_graph.graph_model import (
    KnowledgeEdge,
    KnowledgeGraph,
    KnowledgeNode,
)


def _make_node(label: str, mastery: float, level: int = 2) -> KnowledgeNode:
    n = KnowledgeNode()
    n.label = label
    n.mastery = mastery
    n.level = level
    return n


class TestTopologicalSortWeak(unittest.TestCase):
    """Tests for _topological_sort_weak — no I/O, no LLM."""

    def test_empty_returns_empty(self):
        graph = KnowledgeGraph()
        result = _topological_sort_weak([], graph)
        self.assertEqual(result, [])

    def test_no_edges_returns_mastery_order(self):
        nodes = [
            _make_node("B", 0.2),
            _make_node("A", 0.1),
            _make_node("C", 0.05),
        ]
        graph = KnowledgeGraph(nodes=nodes)
        result = _topological_sort_weak(nodes, graph)
        masteries = [n.mastery for n in result]
        self.assertEqual(masteries, sorted(masteries))

    def test_prerequisite_edge_respected(self):
        a = _make_node("A", 0.1)
        b = _make_node("B", 0.05)
        edge = KnowledgeEdge(source_id=a.id, target_id=b.id, relation="prerequisite")
        graph = KnowledgeGraph(nodes=[a, b], edges=[edge])
        result = _topological_sort_weak([a, b], graph)
        ids = [n.id for n in result]
        # A must come before B (A is prerequisite of B)
        self.assertLess(ids.index(a.id), ids.index(b.id))


class TestGeneratePlanLogic(unittest.TestCase):
    """Tests for generate_plan — covers the mixed-mastery bug fix."""

    def _run(self, coro):
        import asyncio
        return asyncio.get_event_loop().run_until_complete(coro)

    def _make_graph(self, mastery_values: list[float]) -> KnowledgeGraph:
        nodes = [_make_node(f"topic_{i}", m) for i, m in enumerate(mastery_values)]
        return KnowledgeGraph(nodes=nodes)

    def test_all_zero_mastery_new_kb(self):
        """All-zero KB (brand new): plan should cover all nodes, not return 'no weak points'."""
        graph = self._make_graph([0.0, 0.0, 0.0])
        # load_graph is imported lazily inside generate_plan, so patch at source
        with (
            patch("deeptutor.services.knowledge_graph.graph_store.load_graph", return_value=graph),
            patch("deeptutor.capabilities.learning_guide._llm_enhance_topics", new=AsyncMock(side_effect=lambda topics, kb: topics)),
        ):
            plan = self._run(generate_plan("test_kb"))

        self.assertIsNotNone(plan)
        # Must include all 3 unstudied nodes — not "no weak points"
        self.assertEqual(plan["total_weak_points"], 3)
        self.assertGreater(plan["estimated_days"], 0)
        self.assertGreater(len(plan["daily_plans"]), 0)

    def test_mixed_zero_and_weak_mastery(self):
        """Mixed KB (some mastery=0, some mastery=0.15): plan must include BOTH groups."""
        # Bug: before fix, get_weak_nodes filtered mastery > 0 so mastery=0 nodes were missed
        graph = self._make_graph([0.0, 0.0, 0.15, 0.25])
        with (
            patch("deeptutor.services.knowledge_graph.graph_store.load_graph", return_value=graph),
            patch("deeptutor.capabilities.learning_guide._llm_enhance_topics", new=AsyncMock(side_effect=lambda topics, kb: topics)),
        ):
            plan = self._run(generate_plan("test_kb"))

        self.assertIsNotNone(plan)
        # All 4 nodes are below WEAK_THRESHOLD (0.3), so all must be scheduled
        self.assertEqual(plan["total_weak_points"], 4)

    def test_all_mastered_returns_empty_plan(self):
        """Fully mastered KB (all mastery=1.0): return the 'no weak points' message."""
        graph = self._make_graph([1.0, 1.0])
        with (
            patch("deeptutor.services.knowledge_graph.graph_store.load_graph", return_value=graph),
            patch("deeptutor.capabilities.learning_guide._llm_enhance_topics", new=AsyncMock(side_effect=lambda topics, kb: topics)),
        ):
            plan = self._run(generate_plan("test_kb"))

        self.assertIsNotNone(plan)
        self.assertEqual(plan["total_weak_points"], 0)
        self.assertEqual(plan["daily_plans"], [])
        self.assertIn("message", plan)

    def test_graph_not_found_returns_none(self):
        """Missing graph should return None."""
        with patch("deeptutor.services.knowledge_graph.graph_store.load_graph", return_value=None):
            plan = self._run(generate_plan("missing_kb"))
        self.assertIsNone(plan)

    def test_moderate_mastery_fallback(self):
        """Nodes with 0.3 <= mastery < 1.0 (no weak nodes): fallback plan covers them."""
        # mastery values are all at 0.5 — above WEAK_THRESHOLD, below 1.0
        graph = self._make_graph([0.5, 0.6, 0.7])
        with (
            patch("deeptutor.services.knowledge_graph.graph_store.load_graph", return_value=graph),
            patch("deeptutor.capabilities.learning_guide._llm_enhance_topics", new=AsyncMock(side_effect=lambda topics, kb: topics)),
        ):
            plan = self._run(generate_plan("test_kb"))

        self.assertIsNotNone(plan)
        # Fallback should kick in and schedule all 3 nodes
        self.assertEqual(plan["total_weak_points"], 3)
