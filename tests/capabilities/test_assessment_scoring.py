"""
Tests for AssessmentCapability scoring flow integrity.

Covers:
- submit_answers: no quiz_data → error, not exception
- submit_answers: quiz_data with no questions → error
- choice scoring: exact match, wrong, empty answer, ambiguous input
- fill scoring: exact / acceptable / fallback-to-LLM
- mastery update: verify update_from_quiz_dicts is called with correct args
- summary statistics: total_score, max_score, percentage, correct_count
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from deeptutor.capabilities.assessment import AssessmentCapability


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_quiz(questions: list[dict]) -> dict:
    return {
        "title": "Test Quiz",
        "kb_name": "test_kb",
        "questions": questions,
        "total_score": sum(q.get("score", 3) for q in questions),
    }


def _choice_q(qid: int, answer: str = "A", kp: str = "二次方程") -> dict:
    return {
        "id": qid,
        "type": "choice",
        "question": "下列哪个是二次方程？",
        "options": ["A. x²=1", "B. x=1", "C. x+1=0", "D. 1=1"],
        "answer": answer,
        "knowledge_point": kp,
        "score": 3,
        "explanation": "二次方程最高次为2。",
    }


def _fill_q(qid: int, answer: str = "2", acceptable: list | None = None) -> dict:
    return {
        "id": qid,
        "type": "fill",
        "question": "解方程 x=____",
        "answer": answer,
        "acceptable_answers": acceptable or [],
        "knowledge_point": "方程求解",
        "score": 3,
        "explanation": "直接代入验证。",
    }


CAPABILITY = AssessmentCapability()


# ── submit_answers guard tests ────────────────────────────────────────────────

class TestSubmitAnswersGuards(unittest.IsolatedAsyncioTestCase):

    async def test_no_answers_returns_error(self):
        result = await CAPABILITY.submit_answers(answers=None, quiz_data=_make_quiz([_choice_q(1)]))
        self.assertIn("error", result)

    async def test_no_quiz_data_returns_error(self):
        result = await CAPABILITY.submit_answers(answers={"1": "A"}, quiz_data=None)
        self.assertIn("error", result)

    async def test_empty_questions_in_quiz_data_returns_error(self):
        result = await CAPABILITY.submit_answers(
            answers={"1": "A"}, quiz_data={"questions": []}
        )
        self.assertIn("error", result)


# ── choice scoring ────────────────────────────────────────────────────────────

class TestChoiceScoring(unittest.IsolatedAsyncioTestCase):

    async def _submit_single(self, question: dict, student_answer: str, kb_name: str | None = None):
        quiz = _make_quiz([question])
        with patch("deeptutor.capabilities.assessment.update_from_quiz_dicts"):
            return await CAPABILITY.submit_answers(
                kb_name=kb_name,
                answers={str(question["id"]): student_answer},
                quiz_data=quiz,
            )

    async def test_correct_choice_full_score(self):
        result = await self._submit_single(_choice_q(1, answer="A"), "A")
        self.assertEqual(result["results"][0]["score"], 3)
        self.assertTrue(result["results"][0]["correct"])

    async def test_wrong_choice_zero_score(self):
        result = await self._submit_single(_choice_q(1, answer="A"), "B")
        self.assertEqual(result["results"][0]["score"], 0)
        self.assertFalse(result["results"][0]["correct"])

    async def test_choice_case_insensitive(self):
        result = await self._submit_single(_choice_q(1, answer="A"), "a")
        self.assertTrue(result["results"][0]["correct"])

    async def test_choice_with_prefix_text(self):
        """Student answer 'A. x²=1' should extract 'A' and match."""
        result = await self._submit_single(_choice_q(1, answer="A"), "A. x²=1")
        self.assertTrue(result["results"][0]["correct"])

    async def test_choice_no_valid_letter_is_wrong(self):
        """Student types random text with no A/B/C/D → treated as wrong."""
        result = await self._submit_single(_choice_q(1, answer="A"), "不知道")
        self.assertFalse(result["results"][0]["correct"])
        self.assertEqual(result["results"][0]["score"], 0)


# ── fill scoring ──────────────────────────────────────────────────────────────

class TestFillScoring(unittest.IsolatedAsyncioTestCase):

    async def _submit_fill(self, q: dict, student_answer: str, llm_result: dict | None = None):
        quiz = _make_quiz([q])
        llm_result = llm_result or {"score": 0, "correct": False, "feedback": "wrong"}
        mock_complete = AsyncMock(return_value='{"score": 0, "correct": false, "feedback": "wrong"}')
        with (
            patch("deeptutor.capabilities.assessment.complete", mock_complete),
            patch("deeptutor.capabilities.assessment.update_from_quiz_dicts"),
        ):
            return await CAPABILITY.submit_answers(
                answers={str(q["id"]): student_answer},
                quiz_data=quiz,
            )

    async def test_exact_fill_match(self):
        q = _fill_q(1, answer="2")
        result = await self._submit_fill(q, "2")
        self.assertTrue(result["results"][0]["correct"])
        self.assertEqual(result["results"][0]["score"], 3)

    async def test_fill_acceptable_answer(self):
        q = _fill_q(1, answer="1/2", acceptable=["0.5"])
        result = await self._submit_fill(q, "0.5")
        self.assertTrue(result["results"][0]["correct"])

    async def test_fill_whitespace_normalized(self):
        """Answer with extra spaces should match after normalization."""
        q = _fill_q(1, answer="x=2")
        result = await self._submit_fill(q, " x = 2 ")
        # normalize strips spaces → "x=2" == "x=2"
        self.assertTrue(result["results"][0]["correct"])

    async def test_fill_wrong_falls_to_llm_and_fails(self):
        """Wrong answer with no exact match falls to LLM → returns LLM result (score=0)."""
        q = _fill_q(1, answer="2")
        result = await self._submit_fill(q, "99999")
        # LLM returned score=0
        self.assertEqual(result["results"][0]["score"], 0)


# ── summary statistics ────────────────────────────────────────────────────────

class TestSummaryStatistics(unittest.IsolatedAsyncioTestCase):

    async def test_summary_fields_present(self):
        quiz = _make_quiz([_choice_q(1, answer="A"), _choice_q(2, answer="B")])
        with patch("deeptutor.capabilities.assessment.update_from_quiz_dicts"):
            result = await CAPABILITY.submit_answers(
                answers={"1": "A", "2": "C"},  # q1 correct, q2 wrong
                quiz_data=quiz,
            )
        summary = result["summary"]
        self.assertIn("total_score", summary)
        self.assertIn("max_score", summary)
        self.assertIn("percentage", summary)
        self.assertIn("correct_count", summary)
        self.assertIn("total_count", summary)
        self.assertIn("weak_points", summary)

    async def test_all_correct_percentage_100(self):
        quiz = _make_quiz([_choice_q(1, answer="A")])
        with patch("deeptutor.capabilities.assessment.update_from_quiz_dicts"):
            result = await CAPABILITY.submit_answers(
                answers={"1": "A"},
                quiz_data=quiz,
            )
        self.assertEqual(result["summary"]["percentage"], 100.0)
        self.assertEqual(result["summary"]["correct_count"], 1)

    async def test_all_wrong_percentage_zero(self):
        quiz = _make_quiz([_choice_q(1, answer="A")])
        with patch("deeptutor.capabilities.assessment.update_from_quiz_dicts"):
            result = await CAPABILITY.submit_answers(
                answers={"1": "D"},
                quiz_data=quiz,
            )
        self.assertEqual(result["summary"]["total_score"], 0)
        self.assertEqual(result["summary"]["correct_count"], 0)

    async def test_partial_answer_max_score_matches_answered_questions_only(self):
        """max_score should reflect only answered questions, not the whole quiz."""
        quiz = _make_quiz([_choice_q(1, answer="A"), _choice_q(2, answer="B")])
        with patch("deeptutor.capabilities.assessment.update_from_quiz_dicts"):
            result = await CAPABILITY.submit_answers(
                answers={"1": "A"},  # only answer q1
                quiz_data=quiz,
            )
        # max_score = score of q1 only = 3
        self.assertEqual(result["summary"]["max_score"], 3)
        self.assertEqual(result["summary"]["total_count"], 1)

    async def test_weak_points_populated_on_wrong_answers(self):
        quiz = _make_quiz([_choice_q(1, answer="A", kp="一元二次方程")])
        with patch("deeptutor.capabilities.assessment.update_from_quiz_dicts"):
            result = await CAPABILITY.submit_answers(
                answers={"1": "D"},
                quiz_data=quiz,
            )
        self.assertIn("一元二次方程", result["summary"]["weak_points"])


# ── mastery update integration ────────────────────────────────────────────────

class TestMasteryUpdateCalled(unittest.IsolatedAsyncioTestCase):

    async def test_mastery_update_called_with_correct_args(self):
        """update_from_quiz_dicts must be called with (kb_name, list_of_dicts)."""
        quiz = _make_quiz([_choice_q(1, answer="A", kp="二次方程")])
        with patch(
            "deeptutor.capabilities.assessment.update_from_quiz_dicts"
        ) as mock_update:
            await CAPABILITY.submit_answers(
                kb_name="my_kb",
                answers={"1": "A"},
                quiz_data=quiz,
            )
        mock_update.assert_called_once()
        call_args = mock_update.call_args
        assert call_args[0][0] == "my_kb"
        quiz_results = call_args[0][1]
        self.assertEqual(len(quiz_results), 1)
        self.assertIn("is_correct", quiz_results[0])
        self.assertIn("topic", quiz_results[0])
        self.assertTrue(quiz_results[0]["is_correct"])

    async def test_mastery_update_not_called_without_kb_name(self):
        """If kb_name is None, mastery update must be skipped entirely."""
        quiz = _make_quiz([_choice_q(1, answer="A", kp="二次方程")])
        with patch(
            "deeptutor.capabilities.assessment.update_from_quiz_dicts"
        ) as mock_update:
            await CAPABILITY.submit_answers(
                kb_name=None,
                answers={"1": "A"},
                quiz_data=quiz,
            )
        mock_update.assert_not_called()

    async def test_mastery_update_not_called_without_knowledge_point(self):
        """Questions with no knowledge_point contribute nothing to mastery update."""
        q = _choice_q(1, answer="A", kp="")  # empty kp
        quiz = _make_quiz([q])
        with patch(
            "deeptutor.capabilities.assessment.update_from_quiz_dicts"
        ) as mock_update:
            await CAPABILITY.submit_answers(
                kb_name="my_kb",
                answers={"1": "A"},
                quiz_data=quiz,
            )
        # No results with kp → update not called
        mock_update.assert_not_called()


if __name__ == "__main__":
    unittest.main()
