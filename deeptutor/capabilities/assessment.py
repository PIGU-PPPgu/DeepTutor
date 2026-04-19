"""
Assessment Capability
======================

中考风格自适应测评引擎。

功能：
- 多题型支持：选择题、填空题、计算题、简答题/证明题
- 自适应出题：根据知识图谱掌握度选题，薄弱点多出
- 难度自适应：答对加难，答错降难
- 自动评分 + LLM 评分
- 评分结果写入知识图谱（更新 mastery）

API 端点（通过 API router 注册）：
- POST /api/v1/assessment/{kb_name}/generate — 生成一套测试题
- POST /api/v1/assessment/{kb_name}/submit — 提交答案并评分

Stages: generate → evaluate → feedback
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
from datetime import datetime
from typing import Any

from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.services.llm import complete
from deeptutor.services.llm.config import get_llm_config
from deeptutor.services.knowledge_graph.graph_store import load_graph
from deeptutor.services.knowledge_graph.mastery_tracker import (
    QuizResult,
    update_from_quiz,
)

logger = logging.getLogger(__name__)

# ── 常量 ────────────────────────────────────────────────────────────────

QUESTION_TYPES = ["choice", "fill", "calculation", "short_answer"]
DIFFICULTY_LEVELS = ["easy", "medium", "hard"]

# 默认题型分布（共 num_questions 题）
DEFAULT_TYPE_DISTRIBUTION = {
    "choice": 0.35,
    "fill": 0.25,
    "calculation": 0.20,
    "short_answer": 0.20,
}

# 分值配置
SCORE_MAP = {
    "choice": 3,
    "fill": 3,
    "calculation": 8,
    "short_answer": 6,
}

# 难度 → 掌握度阈值（出题时选题用）
DIFFICULTY_MASTERY_RANGE = {
    "easy": (0.0, 0.4),
    "medium": (0.3, 0.7),
    "hard": (0.6, 1.0),
}

# 难度自适应：答对 → 难度变化
DIFFICULTY_SHIFT_ON_CORRECT = {"easy": "medium", "medium": "hard", "hard": "hard"}
DIFFICULTY_SHIFT_ON_WRONG = {"easy": "easy", "medium": "easy", "hard": "medium"}


# ── Prompt 模板 ─────────────────────────────────────────────────────────

GENERATE_CHOICE_PROMPT = """你是一位资深中考命题专家。请根据给定的知识点和难度，生成一道**选择题**（4选1）。

要求：
1. 题目贴近中考真题风格
2. 四个选项 A/B/C/D，只有一个正确答案
3. 干扰项要有迷惑性，设计常见错误（如：符号错误、概念混淆、计算漏步）
4. 标注考察的知识点

知识点：{knowledge_points}
难度：{difficulty}（easy=基础题, medium=中档题, hard=难题/压轴题）
学科：{subject}

请严格以 JSON 格式输出（不要其他文字）：
{{
  "type": "choice",
  "difficulty": "{difficulty}",
  "knowledge_point": "具体知识点",
  "question": "题目内容（完整的题目文本）",
  "options": ["A. 选项一", "B. 选项二", "C. 选项三", "D. 选项四"],
  "answer": "正确选项字母，如A",
  "distractor_analysis": "干扰项设计思路",
  "score": {score},
  "explanation": "详细解析，包含解题思路和关键步骤"
}}"""

GENERATE_FILL_PROMPT = """你是一位资深中考命题专家。请根据给定的知识点和难度，生成一道**填空题**。

要求：
1. 题目贴近中考真题风格
2. 可以有一个或多个空（用____标注）
3. 答案要精确（数值需要化简、带单位等）
4. 标注考察的知识点

知识点：{knowledge_points}
难度：{difficulty}
学科：{subject}

请严格以 JSON 格式输出（不要其他文字）：
{{
  "type": "fill",
  "difficulty": "{difficulty}",
  "knowledge_point": "具体知识点",
  "question": "题目内容，空用____标注",
  "answer": "标准答案（多空用；分隔）",
  "acceptable_answers": ["可接受的其他等价答案"],
  "score": {score},
  "explanation": "详细解析"
}}"""

GENERATE_CALCULATION_PROMPT = """你是一位资深中考命题专家。请根据给定的知识点和难度，生成一道**计算题**。

要求：
1. 题目贴近中考真题风格，有完整的计算过程
2. 标注每一步骤的分值
3. 提供完整的标准解题步骤
4. 标注考察的知识点

知识点：{knowledge_points}
难度：{difficulty}
学科：{subject}

请严格以 JSON 格式输出（不要其他文字）：
{{
  "type": "calculation",
  "difficulty": "{difficulty}",
  "knowledge_point": "具体知识点",
  "question": "题目内容",
  "answer": "最终答案",
  "steps": [
    {{"step": 1, "content": "步骤描述", "score": 2}},
    {{"step": 2, "content": "步骤描述", "score": 2}},
    {{"step": 3, "content": "最终答案", "score": 4}}
  ],
  "key_formulas": ["关键公式列表"],
  "score": {score},
  "explanation": "完整解题过程"
}}"""

GENERATE_SHORT_ANSWER_PROMPT = """你是一位资深中考命题专家。请根据给定的知识点和难度，生成一道**简答题/证明题**。

要求：
1. 题目贴近中考真题风格
2. 提供标准答案和评分要点
3. 列出答案中必须包含的关键词/关键步骤
4. 标注考察的知识点

知识点：{knowledge_points}
难度：{difficulty}
学科：{subject}

请严格以 JSON 格式输出（不要其他文字）：
{{
  "type": "short_answer",
  "difficulty": "{difficulty}",
  "knowledge_point": "具体知识点",
  "question": "题目内容",
  "answer": "标准答案",
  "key_points": ["评分要点1", "评分要点2", "评分要点3"],
  "keywords": ["必须包含的关键词"],
  "score": {score},
  "explanation": "详细解析"
}}"""

EVALUATE_CHOICE_PROMPT = """批改选择题。

题目：{question}
选项：{options}
正确答案：{answer}
学生答案：{student_answer}

直接返回 JSON：
{{"score": {max_score}, "correct": true/false, "feedback": "简短反馈"}}"""

EVALUATE_FILL_PROMPT = """批改填空题。

题目：{question}
标准答案：{answer}
可接受答案：{acceptable_answers}
学生答案：{student_answer}

判断逻辑：精确匹配或等价判断（如分数化简、单位换算）。

直接返回 JSON：
{{"score": {max_score}, "correct": true/false, "feedback": "指出差异和正确答案"}}"""

EVALUATE_CALCULATION_PROMPT = """批改计算题。

题目：{question}
标准解题步骤：{steps}
最终答案：{answer}
满分：{max_score}分

学生答案：
{student_answer}

评分规则：
- 每个正确步骤按步骤分得分
- 最终答案正确额外得分
- 方法正确但计算错误酌情给分

直接返回 JSON：
{{
  "score": 得分,
  "correct": true/false,
  "step_scores": [{{"step": 1, "earned": 2, "max": 2}}],
  "feedback": "详细反馈，指出哪步对哪步错",
  "weak_point": "如果答错，指出具体薄弱环节"
}}"""

EVALUATE_SHORT_ANSWER_PROMPT = """批改简答题/证明题。

题目：{question}
标准答案：{answer}
评分要点：{key_points}
关键词：{keywords}
满分：{max_score}分

学生答案：
{student_answer}

评分规则：
- 检查每个评分要点的覆盖程度
- 检查关键词出现情况
- 综合评分

直接返回 JSON：
{{
  "score": 得分,
  "correct": true/false,
  "covered_points": ["已覆盖的要点"],
  "missing_points": ["缺失的要点"],
  "feedback": "详细反馈",
  "weak_point": "薄弱知识点"
}}"""


# ── 辅助函数 ────────────────────────────────────────────────────────────

def _question_fingerprint(q: dict) -> str:
    """生成题目指纹，用于去重。"""
    text = q.get("question", "") + q.get("knowledge_point", "")
    return hashlib.md5(text.encode()).hexdigest()[:12]


def _select_difficulty(current_mastery: float | None) -> str:
    """根据掌握度选择初始难度。"""
    if current_mastery is None:
        return "medium"
    if current_mastery < 0.3:
        return "easy"
    elif current_mastery < 0.6:
        return "medium"
    else:
        return "hard"


def _adjust_difficulty(current: str, correct: bool) -> str:
    """自适应调整难度。"""
    if correct:
        return DIFFICULTY_SHIFT_ON_CORRECT.get(current, current)
    return DIFFICULTY_SHIFT_ON_WRONG.get(current, current)


def _get_weak_nodes(kb_name: str, top_n: int = 10) -> list[dict]:
    """从知识图谱获取薄弱知识点。"""
    graph = load_graph(kb_name)
    if not graph or not graph.nodes:
        return []
    # 按 mastery 升序排列，取最薄弱的
    sorted_nodes = sorted(graph.nodes, key=lambda n: n.mastery)
    return [
        {"id": n.id, "label": n.label, "mastery": n.mastery}
        for n in sorted_nodes[:top_n]
    ]


def _get_all_knowledge_points(kb_name: str) -> list[dict]:
    """获取知识图谱中所有知识点。"""
    graph = load_graph(kb_name)
    if not graph or not graph.nodes:
        return []
    return [
        {"id": n.id, "label": n.label, "mastery": n.mastery, "level": n.level}
        for n in graph.nodes
        if n.level >= 2  # 知识点级别
    ]


def _plan_question_distribution(
    num_questions: int,
    difficulty: str | None = None,
    topic_filter: list[str] | None = None,
    kb_name: str | None = None,
) -> list[dict]:
    """
    自适应规划题目分布。
    返回 [{type, difficulty, knowledge_points, score}] 列表。
    """
    plan = []
    remaining = num_questions

    # 获取知识点
    kp_nodes = []
    if kb_name:
        all_kps = _get_all_knowledge_points(kb_name)
        if topic_filter:
            all_kps = [k for k in all_kps if any(t in k["label"] for t in topic_filter)]
        # 按掌握度排序（薄弱的优先）
        all_kps.sort(key=lambda k: k["mastery"])
        kp_nodes = all_kps

    # 分配题型
    type_counts = {}
    for qtype, ratio in DEFAULT_TYPE_DISTRIBUTION.items():
        count = max(1, round(num_questions * ratio))
        type_counts[qtype] = count

    # 调整总数
    total = sum(type_counts.values())
    while total > num_questions:
        max_type = max(type_counts, key=type_counts.get)
        type_counts[max_type] -= 1
        total -= 1
    while total < num_questions:
        type_counts["choice"] += 1
        total += 1

    kp_idx = 0
    for qtype, count in type_counts.items():
        for i in range(count):
            # 确定难度
            if difficulty:
                q_diff = difficulty
            elif kp_nodes:
                node = kp_nodes[kp_idx % len(kp_nodes)]
                q_diff = _select_difficulty(node["mastery"])
            else:
                q_diff = random.choice(DIFFICULTY_LEVELS)

            # 选择知识点
            if kp_nodes:
                node = kp_nodes[kp_idx % len(kp_nodes)]
                kp_text = node["label"]
                kp_idx += 1
            else:
                kp_text = ""

            plan.append({
                "type": qtype,
                "difficulty": q_diff,
                "knowledge_points": kp_text,
                "score": SCORE_MAP.get(qtype, 3),
            })

    random.shuffle(plan)
    return plan


def _parse_json_response(response: str) -> dict[str, Any]:
    """从 LLM 响应中解析 JSON。"""
    text = response.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse JSON: %s", text[:200])
        return {}


# ── Capability 实现 ─────────────────────────────────────────────────────

class AssessmentCapability(BaseCapability):
    """中考风格自适应测评引擎。"""

    manifest = CapabilityManifest(
        name="assessment",
        description="自适应测评引擎：根据知识图谱生成中考风格题目，支持多种题型和智能评分。",
        stages=["generate", "evaluate", "feedback"],
        tools_used=[],
        cli_aliases=["test", "quiz", "assess"],
        config_defaults={"temperature": 0.3},
    )

    # 记录已出过的题目指纹，避免重复（实例级别，避免并发污染）
    def __init__(self) -> None:
        self._used_fingerprints: set[str] = set()

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        """运行测评流程（兼容旧版 context 调用）。"""
        content = context.user_message or ""
        metadata = getattr(context, "metadata", {}) or {}

        kb_name = metadata.get("kb_name")
        num_questions = metadata.get("num_questions", 8)
        difficulty = metadata.get("difficulty")
        topic_filter = metadata.get("topic_filter")
        student_answers = metadata.get("answers")
        quiz_data = metadata.get("quiz_data")

        # 如果有学生答案，执行评分
        if student_answers:
            await self._run_evaluate(kb_name, student_answers, stream, quiz_data=quiz_data)
            return

        # 否则生成题目
        quiz = await self.generate_quiz(
            kb_name=kb_name,
            num_questions=num_questions,
            difficulty=difficulty,
            topic_filter=topic_filter,
            content=content,
        )

        async with stream.stage("generate", source=self.manifest.name):
            markdown = self.format_quiz_markdown(quiz)
            await stream.content(markdown, source=self.manifest.name,
                                 metadata={"quiz": quiz, "quiz_data": quiz})

    async def _run_evaluate(
        self, kb_name: str | None, answers: dict, stream: StreamBus,
        quiz_data: dict[str, Any] | None = None,
    ) -> None:
        """执行评分并输出结果。"""
        async with stream.stage("evaluate", source=self.manifest.name):
            await stream.thinking("正在批改...", source=self.manifest.name)
            result = await self.submit_answers(kb_name=kb_name, answers=answers, quiz_data=quiz_data)
            eval_md = self.format_evaluation_markdown(result)
            await stream.content(eval_md, source=self.manifest.name,
                                 metadata={"evaluation": result})

    # ── 核心 API ──

    async def generate_quiz(
        self,
        kb_name: str | None = None,
        num_questions: int = 8,
        difficulty: str | None = None,
        topic_filter: list[str] | None = None,
        content: str | None = None,
        subject: str = "数学",
    ) -> dict[str, Any]:
        """生成一套测评题。"""
        llm_config = get_llm_config()

        # 规划题目分布
        plan = _plan_question_distribution(
            num_questions=num_questions,
            difficulty=difficulty,
            topic_filter=topic_filter,
            kb_name=kb_name,
        )

        questions = []
        total_score = 0
        seen = set()

        for item in plan:
            q = await self._generate_single_question(
                qtype=item["type"],
                difficulty=item["difficulty"],
                knowledge_points=item["knowledge_points"] or (content or "")[:500],
                subject=subject,
                score=item["score"],
                llm_config=llm_config,
            )
            if not q:
                continue

            # 去重
            fp = _question_fingerprint(q)
            if fp in seen:
                continue
            seen.add(fp)

            q["id"] = len(questions) + 1
            questions.append(q)
            total_score += q.get("score", 3)

        return {
            "title": f"自适应测评 - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "kb_name": kb_name,
            "questions": questions,
            "total_score": total_score,
            "metadata": {
                "num_questions": len(questions),
                "difficulty": difficulty,
                "topic_filter": topic_filter,
            },
        }

    async def submit_answers(
        self,
        kb_name: str | None = None,
        answers: dict[str, str] | None = None,
        quiz_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        提交答案并评分。

        answers: {question_id: student_answer}
        quiz_data: 原始题目数据（含标准答案），如不提供则从 kb_name 加载最近测试
        """
        if not answers:
            return {"error": "未提供答案"}

        llm_config = get_llm_config()
        questions = quiz_data.get("questions", []) if quiz_data else []
        if not questions:
            return {"error": "未找到题目数据"}

        results = []
        quiz_results_for_mastery = []  # 用于更新知识图谱
        current_difficulty = "medium"

        for q in questions:
            qid = str(q.get("id", ""))
            if qid not in answers:
                continue

            student_answer = answers[qid]
            qtype = q.get("type", "choice")

            eval_result = await self._evaluate_single(
                question=q,
                student_answer=student_answer,
                qtype=qtype,
                llm_config=llm_config,
            )

            eval_result["question_id"] = qid
            eval_result["question_type"] = qtype
            eval_result["knowledge_point"] = q.get("knowledge_point", "")
            results.append(eval_result)

            # 难度自适应
            current_difficulty = _adjust_difficulty(
                current_difficulty, eval_result.get("correct", False)
            )

            # 收集 mastery 更新数据
            kp = q.get("knowledge_point", "")
            if kp and kb_name:
                quiz_results_for_mastery.append({
                    "question": q.get("question", ""),
                    "is_correct": eval_result.get("correct", False),
                    "topic": kp,
                })

        # 更新知识图谱
        if kb_name and quiz_results_for_mastery:
            try:
                from deeptutor.services.knowledge_graph.mastery_tracker import (
                    update_from_quiz_dicts,
                )
                update_from_quiz_dicts(kb_name, quiz_results_for_mastery)
            except Exception as e:
                logger.warning("Failed to update mastery: %s", e)

        # 统计
        total_earned = sum(r.get("score", 0) for r in results)
        total_max = sum(q.get("score", 0) for q in questions if str(q.get("id", "")) in (answers or {}))
        correct_count = sum(1 for r in results if r.get("correct"))

        return {
            "results": results,
            "summary": {
                "total_score": total_earned,
                "max_score": total_max,
                "percentage": round(total_earned / max(total_max, 1) * 100, 1),
                "correct_count": correct_count,
                "total_count": len(results),
                "weak_points": list({
                    r.get("weak_point", "")
                    for r in results
                    if r.get("weak_point")
                }),
            },
        }

    # ── 单题生成 ──

    async def _generate_single_question(
        self,
        qtype: str,
        difficulty: str,
        knowledge_points: str,
        subject: str,
        score: int,
        llm_config: Any = None,
    ) -> dict[str, Any] | None:
        """生成单道题目。"""
        prompt_map = {
            "choice": GENERATE_CHOICE_PROMPT,
            "fill": GENERATE_FILL_PROMPT,
            "calculation": GENERATE_CALCULATION_PROMPT,
            "short_answer": GENERATE_SHORT_ANSWER_PROMPT,
        }
        template = prompt_map.get(qtype)
        if not template:
            return None

        prompt = template.format(
            knowledge_points=knowledge_points[:1000],
            difficulty=difficulty,
            subject=subject,
            score=score,
        )

        try:
            response = await complete(
                prompt=prompt,
                system_prompt="你是一个 JSON 输出机器，只输出合法 JSON，不要输出任何其他文字。",
                temperature=0.4,
                max_tokens=2000,
            )
            result = _parse_json_response(response)
            if result and result.get("question"):
                result["type"] = qtype
                return result
            return None
        except Exception as e:
            logger.error("Generate question failed (%s): %s", qtype, e)
            return None

    # ── 单题评分 ──

    async def _evaluate_single(
        self,
        question: dict,
        student_answer: str,
        qtype: str,
        llm_config: Any = None,
    ) -> dict[str, Any]:
        """评分单道题。"""
        max_score = question.get("score", 3)

        # 选择题 / 填空题：优先精确匹配
        if qtype == "choice":
            return self._evaluate_choice(question, student_answer, max_score)
        elif qtype == "fill":
            exact = self._evaluate_fill_exact(question, student_answer, max_score)
            if exact is not None:
                return exact

        # 计算题 / 简答题 / 填空题（精确匹配失败）：LLM 评分
        return await self._evaluate_by_llm(question, student_answer, qtype, max_score)

    def _evaluate_choice(
        self, question: dict, student_answer: str, max_score: int
    ) -> dict[str, Any]:
        """选择题精确匹配评分。"""
        correct_answer = question.get("answer", "").strip().upper()
        student = student_answer.strip().upper()

        # 提取字母
        correct_letter = correct_answer[0] if correct_answer else ""
        student_letter = ""
        for ch in student:
            if ch in "ABCD":
                student_letter = ch
                break

        is_correct = student_letter == correct_letter
        return {
            "score": max_score if is_correct else 0,
            "correct": is_correct,
            "feedback": (
                f"✅ 正确！答案是 {correct_letter}。{question.get('explanation', '')}"
                if is_correct
                else f"❌ 错误。你选了 {student_letter or '（无效选项）'}，正确答案是 {correct_letter}。{question.get('explanation', '')}"
            ),
            "weak_point": "" if is_correct else question.get("knowledge_point", ""),
        }

    def _evaluate_fill_exact(
        self, question: dict, student_answer: str, max_score: int
    ) -> dict[str, Any] | None:
        """填空题精确匹配评分。返回 None 表示需要 LLM 评分。"""
        correct = question.get("answer", "").strip()
        acceptable = question.get("acceptable_answers", [])
        student = student_answer.strip()

        # 标准化比较
        def normalize(s: str) -> str:
            return s.replace(" ", "").replace("　", "").lower()

        norm_correct = normalize(correct)
        norm_student = normalize(student)

        if norm_student == norm_correct:
            return {
                "score": max_score,
                "correct": True,
                "feedback": f"✅ 正确！{question.get('explanation', '')}",
                "weak_point": "",
            }

        # 检查可接受答案
        for alt in acceptable:
            if normalize(str(alt)) == norm_student:
                return {
                    "score": max_score,
                    "correct": True,
                    "feedback": f"✅ 正确！（等价答案）{question.get('explanation', '')}",
                    "weak_point": "",
                }

        # 完全不匹配，交给 LLM 判断等价性
        return None

    async def _evaluate_by_llm(
        self,
        question: dict,
        student_answer: str,
        qtype: str,
        max_score: int,
    ) -> dict[str, Any]:
        """LLM 评分（计算题、简答题、填空题等价判断）。"""
        prompt_map = {
            "fill": EVALUATE_FILL_PROMPT,
            "calculation": EVALUATE_CALCULATION_PROMPT,
            "short_answer": EVALUATE_SHORT_ANSWER_PROMPT,
        }
        template = prompt_map.get(qtype, EVALUATE_SHORT_ANSWER_PROMPT)

        prompt = template.format(
            question=question.get("question", ""),
            options=question.get("options", []),
            answer=question.get("answer", ""),
            acceptable_answers=question.get("acceptable_answers", []),
            steps=question.get("steps", []),
            key_points=question.get("key_points", []),
            keywords=question.get("keywords", []),
            student_answer=student_answer,
            max_score=max_score,
        )

        try:
            response = await complete(
                prompt=prompt,
                system_prompt="你是一个 JSON 输出机器，只输出合法 JSON。",
                temperature=0.2,
                max_tokens=800,
            )
            result = _parse_json_response(response)
            # 确保 score 在合理范围
            result["score"] = min(max(0, result.get("score", 0)), max_score)
            result["correct"] = result.get("score", 0) >= max_score * 0.8
            return result
        except Exception as e:
            logger.warning("LLM evaluation failed: %s", e)
            return {
                "score": 0,
                "correct": False,
                "feedback": f"评分失败: {e}",
                "weak_point": question.get("knowledge_point", ""),
            }

    # ── 格式化输出 ──

    @staticmethod
    def format_quiz_markdown(quiz_data: dict[str, Any]) -> str:
        """将测评题格式化为 Markdown。"""
        title = quiz_data.get("title", "知识测评")
        questions = quiz_data.get("questions", [])
        total = quiz_data.get("total_score", 0)

        lines = [f"## 📝 {title}\n"]
        lines.append(f"**总分：{total}分 | 共{len(questions)}题**\n")

        type_labels = {
            "choice": "选择题",
            "fill": "填空题",
            "calculation": "计算题",
            "short_answer": "简答题",
        }
        diff_labels = {"easy": "⭐", "medium": "⭐⭐", "hard": "⭐⭐⭐"}

        # 按题型分组
        by_type: dict[str, list] = {}
        for q in questions:
            by_type.setdefault(q.get("type", ""), []).append(q)

        for qtype, type_qs in by_type.items():
            label = type_labels.get(qtype, "题")
            lines.append(f"### 一、{label}（共{len(type_qs)}题）\n")

            for q in type_qs:
                qid = q.get("id", "?")
                diff = diff_labels.get(q.get("difficulty", ""), "")
                score = q.get("score", 3)
                lines.append(f"**{qid}.** （{score}分）{diff}")
                lines.append(f"\n{q.get('question', '')}\n")
                for opt in q.get("options", []):
                    lines.append(f"  {opt}")
                if q.get("options"):
                    lines.append("")
                lines.append(f"<details><summary>📝 查看答案与解析</summary>")
                lines.append(f"\n**答案**：{q.get('answer', '')}")
                lines.append(f"\n**解析**：{q.get('explanation', '')}")
                lines.append(f"\n**知识点**：{q.get('knowledge_point', '')}\n")
                lines.append("</details>\n")

        return "\n".join(lines)

    @staticmethod
    def format_evaluation_markdown(evaluation: dict[str, Any]) -> str:
        """将评分结果格式化为 Markdown。"""
        results = evaluation.get("results", [])
        summary = evaluation.get("summary", {})

        lines = ["## 📊 批改结果\n"]
        lines.append(
            f"**得分：{summary.get('total_score', 0)}/{summary.get('max_score', 0)}"
            f"（{summary.get('percentage', 0)}%）**\n"
        )

        for r in results:
            qid = r.get("question_id", "?")
            score = r.get("score", 0)
            correct = r.get("correct", False)
            icon = "✅" if correct else "❌"
            kp = r.get("knowledge_point", "")
            kp_str = f"（{kp}）" if kp else ""
            lines.append(f"**第{qid}题** {icon} {score}分 {kp_str}")
            lines.append(f"> {r.get('feedback', '')}\n")

        weak_points = summary.get("weak_points", [])
        if weak_points:
            lines.append("### 🎯 薄弱知识点")
            for wp in weak_points:
                lines.append(f"- {wp}")

        lines.append(f"\n---\n*正确率：{summary.get('correct_count', 0)}/{summary.get('total_count', 0)}*")
        return "\n".join(lines)
