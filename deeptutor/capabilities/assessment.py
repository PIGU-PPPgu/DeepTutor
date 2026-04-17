"""
Assessment Capability
======================

多题型测评引擎：对标中考题型。

Stages: generate → format → evaluate

设计目标：根据学习内容自动生成中考风格测评题，支持批改和薄弱知识点标注。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.services.llm import complete
from deeptutor.services.llm.config import get_llm_config

logger = logging.getLogger(__name__)

# ── Prompt 模板 ─────────────────────────────────────────────────────────

GENERATE_PROMPT = """你是一位资深中考命题专家。请根据以下学习内容生成一套测评题。

要求：
1. 题型组合：选择题（3-4题）、填空题（2-3题）、判断题（2-3题）、简答题（1-2题）
2. 如果内容涉及计算，加入计算题（1-2题）
3. 难度分布：简单40%、中等40%、困难20%
4. 每题标注知识点和难度等级
5. 每题必须有标准答案和详细解析
6. 对标中考出题风格

请严格以 JSON 格式输出（不要其他文字）：
{{
  "title": "测评标题",
  "questions": [
    {{
      "id": 1,
      "type": "choice|fill|judge|short_answer|calculation",
      "difficulty": "easy|medium|hard",
      "knowledge_point": "知识点",
      "question": "题目内容",
      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
      "answer": "标准答案",
      "score": 3,
      "explanation": "详细解析"
    }}
  ],
  "total_score": 100
}}

学习内容：
{content}"""

EVALUATE_PROMPT = """你是一位资深阅卷老师。请批改学生的答案。

题目信息：
{question}

标准答案：{standard_answer}
评分标准：{score} 分

学生答案：{student_answer}

请以 JSON 格式返回批改结果（不要其他文字）：
{{
  "score": 得分(数字),
  "correct": true/false,
  "feedback": "详细反馈，指出对错和改进建议",
  "weak_point": "如果答错，标注薄弱知识点，答对则为空字符串"
}}"""


# ── Capability 实现 ─────────────────────────────────────────────────────

class AssessmentCapability(BaseCapability):
    """多题型测评引擎：生成 → 格式化 → 批改。"""

    manifest = CapabilityManifest(
        name="assessment",
        description="多题型测评引擎：根据学习内容自动生成中考风格测评题，支持批改和薄弱知识点分析。",
        stages=["generate", "format", "evaluate"],
        tools_used=[],
        cli_aliases=["test", "quiz", "assess"],
        config_defaults={"temperature": 0.3},
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        content = context.user_message
        if not content or len(content.strip()) < 20:
            await stream.content(
                "内容太短，无法生成测评题。请提供更多学习内容。",
                source=self.manifest.name,
            )
            return

        llm_config = get_llm_config()
        api_key = llm_config.api_key
        base_url = llm_config.base_url
        model = llm_config.model

        # 尝试从 context 中获取学生答案（如有）
        student_answers = self._extract_student_answers(content)

        # ── Stage 1: 生成题目 ──
        async with stream.stage("generate", source=self.manifest.name):
            await stream.thinking("正在生成测评题目...", source=self.manifest.name)
            quiz_data = await self._generate_questions(
                content, api_key, base_url, model
            )
            questions = quiz_data.get("questions", [])
            await stream.observation(
                f"已生成 {len(questions)} 道题目",
                source=self.manifest.name,
                stage="generate",
                metadata={"quiz_data": quiz_data},
            )

        # ── Stage 2: 格式化输出 ──
        async with stream.stage("format", source=self.manifest.name):
            markdown_output = self._format_markdown(quiz_data)
            await stream.content(
                markdown_output,
                source=self.manifest.name,
                stage="format",
                metadata={"json_output": quiz_data},
            )

        # ── Stage 3: 批改评估 ──
        if student_answers and questions:
            async with stream.stage("evaluate", source=self.manifest.name):
                await stream.thinking("正在批改学生答案...", source=self.manifest.name)
                evaluation = await self._evaluate_answers(
                    questions, student_answers, api_key, base_url, model
                )
                eval_output = self._format_evaluation(evaluation)
                await stream.content(
                    eval_output,
                    source=self.manifest.name,
                    stage="evaluate",
                    metadata={"evaluation": evaluation},
                )

    # ── 私有方法 ──

    async def _generate_questions(
        self, content: str, api_key: str, base_url: str, model: str
    ) -> dict[str, Any]:
        prompt = GENERATE_PROMPT.format(content=content[:6000])
        try:
            response = await complete(
                prompt=prompt,
                system_prompt="你是一个 JSON 输出机器，只输出合法 JSON。",
                model=model,
                api_key=api_key,
                base_url=base_url,
                temperature=0.3,
                max_tokens=4000,
            )
            return self._parse_json(response)
        except Exception as e:
            logger.error("Question generation failed: %s", e)
            return {"title": "测评", "questions": [], "total_score": 0}

    async def _evaluate_answers(
        self,
        questions: list[dict[str, Any]],
        student_answers: dict[str, str],
        api_key: str,
        base_url: str,
        model: str,
    ) -> list[dict[str, Any]]:
        results = []
        for q in questions:
            qid = str(q.get("id", ""))
            if qid not in student_answers:
                continue
            prompt = EVALUATE_PROMPT.format(
                question=q.get("question", ""),
                standard_answer=q.get("answer", ""),
                score=q.get("score", 0),
                student_answer=student_answers[qid],
            )
            try:
                response = await complete(
                    prompt=prompt,
                    system_prompt="你是一个 JSON 输出机器，只输出合法 JSON。",
                    model=model,
                    api_key=api_key,
                    base_url=base_url,
                    temperature=0.2,
                    max_tokens=500,
                )
                result = self._parse_json(response)
                result["question_id"] = qid
                result["knowledge_point"] = q.get("knowledge_point", "")
                results.append(result)
            except Exception as e:
                logger.warning("Evaluation failed for Q%s: %s", qid, e)
                results.append({
                    "question_id": qid,
                    "score": 0,
                    "correct": False,
                    "feedback": f"批改失败: {e}",
                    "weak_point": q.get("knowledge_point", ""),
                })
        return results

    @staticmethod
    def _extract_student_answers(content: str) -> dict[str, str]:
        """尝试从输入中解析学生答案。格式：'1:答案 2:答案' 或 JSON。"""
        answers: dict[str, str] = {}
        # 尝试 JSON 格式
        try:
            data = json.loads(content)
            if isinstance(data, dict) and "answers" in data:
                content = data["answers"]
        except (json.JSONDecodeError, TypeError):
            pass
        return answers

    @staticmethod
    def _format_markdown(quiz_data: dict[str, Any]) -> str:
        title = quiz_data.get("title", "知识测评")
        questions = quiz_data.get("questions", [])
        total = quiz_data.get("total_score", 100)

        lines = [f"## 📝 {title}\n"]
        lines.append(f"**总分：{total}分**\n")

        type_labels = {
            "choice": "选择题",
            "fill": "填空题",
            "judge": "判断题",
            "short_answer": "简答题",
            "calculation": "计算题",
        }
        diff_labels = {"easy": "⭐", "medium": "⭐⭐", "hard": "⭐⭐⭐"}

        for q in questions:
            qtype = type_labels.get(q.get("type", ""), "题")
            diff = diff_labels.get(q.get("difficulty", ""), "")
            lines.append(f"### 第{q.get('id', '?')}题（{qtype}，{q.get('score', 0)}分）{diff}")
            lines.append(f"\n{q.get('question', '')}\n")
            for opt in q.get("options", []):
                lines.append(f"- {opt}")
            lines.append(f"\n<details><summary>📝 答案与解析</summary>\n")
            lines.append(f"**答案**：{q.get('answer', '')}\n")
            lines.append(f"**解析**：{q.get('explanation', '')}\n")
            lines.append(f"**知识点**：{q.get('knowledge_point', '')}\n")
            lines.append("</details>\n")

        return "\n".join(lines)

    @staticmethod
    def _format_evaluation(evaluation: list[dict[str, Any]]) -> str:
        lines = ["## 📊 批改结果\n"]
        total_score = 0
        max_score = 0
        weak_points: list[str] = []

        for ev in evaluation:
            qid = ev.get("question_id", "?")
            score = ev.get("score", 0)
            correct = ev.get("correct", False)
            icon = "✅" if correct else "❌"
            lines.append(f"**第{qid}题** {icon} 得分：{score}")
            lines.append(f"> {ev.get('feedback', '')}\n")
            total_score += score
            wp = ev.get("weak_point", "")
            if wp:
                weak_points.append(wp)

        lines.append(f"\n**总分：{total_score}**")
        if weak_points:
            lines.append("\n### 🎯 薄弱知识点")
            for wp in weak_points:
                lines.append(f"- {wp}")

        return "\n".join(lines)

    @staticmethod
    def _parse_json(response: str) -> dict[str, Any]:
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
