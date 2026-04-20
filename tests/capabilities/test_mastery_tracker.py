"""Unit tests for mastery_tracker.update_from_quiz_dicts — pure logic, no I/O."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from deeptutor.services.knowledge_graph.graph_model import KnowledgeGraph, KnowledgeNode
from deeptutor.services.knowledge_graph.mastery_tracker import update_from_quiz_dicts


def _node(label: str, mastery: float = 0.5) -> KnowledgeNode:
    n = KnowledgeNode()
    n.label = label
    n.mastery = mastery
    return n


def _run_update(graph: KnowledgeGraph, results: list[dict]) -> KnowledgeGraph:
    """Run update_from_quiz_dicts with mocked I/O, return updated graph."""
    with (
        patch(
            "deeptutor.services.knowledge_graph.mastery_tracker.load_graph",
            return_value=graph,
        ),
        patch("deeptutor.services.knowledge_graph.mastery_tracker.save_graph"),
    ):
        update_from_quiz_dicts("test_kb", results)
    return graph


class TestUpdateFromQuizDicts(unittest.TestCase):
    """Tests for node-matching and mastery-update logic in update_from_quiz_dicts."""

    # ── Exact matching ──────────────────────────────────────────────────────

    def test_exact_match_updates_correct_node(self):
        """Topic exactly matching a node label updates that node."""
        node = _node("一元二次方程", mastery=0.5)
        graph = KnowledgeGraph(nodes=[node])
        _run_update(graph, [{"topic": "一元二次方程", "is_correct": True, "question": ""}])
        # EMA toward 0.9 (correct target in update_from_quiz_dicts)
        self.assertGreater(node.mastery, 0.5)

    def test_exact_match_correct_increases_mastery(self):
        initial = 0.4
        node = _node("函数", mastery=initial)
        graph = KnowledgeGraph(nodes=[node])
        _run_update(graph, [{"topic": "函数", "is_correct": True, "question": ""}])
        self.assertGreater(node.mastery, initial)

    def test_exact_match_wrong_decreases_mastery(self):
        initial = 0.6
        node = _node("函数", mastery=initial)
        graph = KnowledgeGraph(nodes=[node])
        _run_update(graph, [{"topic": "函数", "is_correct": False, "question": ""}])
        self.assertLess(node.mastery, initial)

    # ── Short generic labels must NOT match specific longer topics ──────────

    def test_short_generic_label_does_not_match_specific_topic(self):
        """'方程' (2 chars) must NOT match topic '一元二次方程' — prevents mastery corruption."""
        generic = _node("方程", mastery=0.5)
        specific = _node("一元二次方程", mastery=0.3)
        graph = KnowledgeGraph(nodes=[generic, specific])
        _run_update(
            graph,
            [{"topic": "一元二次方程", "is_correct": True, "question": "解方程"}],
        )
        # Only the specific node should be updated; generic "方程" must stay at 0.5
        self.assertEqual(generic.mastery, 0.5, "'方程' must not match '一元二次方程'")
        self.assertGreater(specific.mastery, 0.3, "'一元二次方程' must be updated")

    def test_short_label_函数_does_not_match_topic_一次函数(self):
        """'函数' (2 chars) must NOT match '一次函数' via substring."""
        generic = _node("函数", mastery=0.5)
        specific = _node("一次函数", mastery=0.2)
        graph = KnowledgeGraph(nodes=[generic, specific])
        _run_update(
            graph,
            [{"topic": "一次函数", "is_correct": True, "question": ""}],
        )
        self.assertEqual(generic.mastery, 0.5, "'函数' must not match '一次函数'")
        self.assertGreater(specific.mastery, 0.2)

    # ── Longer specific labels should still match correctly ────────────────

    def test_specific_label_matches_when_topic_contains_it(self):
        """'一次方程' (4 chars) IS a substring of '一元一次方程的解' — should match."""
        node = _node("一次方程", mastery=0.3)
        graph = KnowledgeGraph(nodes=[node])
        _run_update(
            graph,
            [{"topic": "一元一次方程的解", "is_correct": True, "question": ""}],
        )
        self.assertGreater(node.mastery, 0.3)

    def test_topic_substring_of_label_matches(self):
        """Topic '一次方程' inside label '一元一次方程': match via 'topic in label'."""
        node = _node("一元一次方程", mastery=0.3)
        graph = KnowledgeGraph(nodes=[node])
        _run_update(
            graph,
            [{"topic": "一次方程", "is_correct": True, "question": ""}],
        )
        self.assertGreater(node.mastery, 0.3)

    # ── No match → no update ───────────────────────────────────────────────

    def test_no_matching_node_no_update(self):
        """Unrelated topic leaves all node masteries unchanged."""
        node = _node("分数", mastery=0.5)
        graph = KnowledgeGraph(nodes=[node])
        _run_update(
            graph,
            [{"topic": "圆的面积", "is_correct": True, "question": ""}],
        )
        self.assertEqual(node.mastery, 0.5)

    def test_missing_graph_does_not_raise(self):
        """Missing graph (load returns None) should not raise."""
        with patch(
            "deeptutor.services.knowledge_graph.mastery_tracker.load_graph",
            return_value=None,
        ):
            # Should return silently
            update_from_quiz_dicts("missing_kb", [{"topic": "函数", "is_correct": True}])

    # ── Empty / edge cases ─────────────────────────────────────────────────

    def test_empty_results_no_update(self):
        node = _node("方程", mastery=0.5)
        graph = KnowledgeGraph(nodes=[node])
        _run_update(graph, [])
        self.assertEqual(node.mastery, 0.5)

    def test_result_without_topic_falls_back_to_question_match(self):
        """No topic provided → falls back to matching label in question text."""
        node = _node("一元二次方程", mastery=0.3)
        graph = KnowledgeGraph(nodes=[node])
        _run_update(
            graph,
            [{"topic": "", "is_correct": True, "question": "解一元二次方程 x²+3x+2=0"}],
        )
        # Label "一元二次方程" appears in the question text → should be updated
        self.assertGreater(node.mastery, 0.3)


if __name__ == "__main__":
    unittest.main()
