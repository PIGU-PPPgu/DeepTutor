"""
Socratic Dialog Capability
==========================

苏格拉底式对话：不给答案，通过提问引导学生自己思考。

Stages: assess → plan → dialog → reflect
"""

from __future__ import annotations

import json
from typing import Any

from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.services.llm import complete
from deeptutor.services.llm.config import get_llm_config

# ---------------------------------------------------------------------------
# Prompt templates (all in Chinese, suitable for 七年级 students)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
你是一位经验丰富的苏格拉底式家教老师，面向初中生（七年级）进行对话引导。

核心原则：
- 绝不直接给出答案
- 通过精心设计的问题引导学生自己思考
- 温和但坚定，鼓励学生表达自己的想法
- 根据学生的回答灵活调整引导策略
- 语言通俗易懂，贴近七年级学生的认知水平
- 同时支持数学和语文场景

你必须在回复中使用以下 JSON 格式（不要添加 markdown 代码块标记）：
{"question": "你要问学生的问题", "reasoning": "你选择这个问题的内部推理", "mode": "concept_check|analogy_guide|counter_example|deep_probe", "confidence": 0.0-1.0}
"""

ASSESS_PROMPT = """\
根据以下对话历史，评估学生对当前知识点的理解程度。

对话历史：
{history}

知识参考：
{knowledge}

请分析学生的理解水平，返回 JSON（不要 markdown 代码块）：
{{
  "level": "初学|部分理解|基本掌握|深入理解",
  "evidence": "判断依据",
  "misconceptions": ["发现的误解或空白"],
  "strengths": ["学生展现的优势"]
}}
"""

PLAN_PROMPT = """\
根据学生评估结果，制定下一步的苏格拉底式对话策略。

学生水平：{level}
发现的误解：{misconceptions}
学生优势：{strengths}
对话历史：{history}

请选择最佳引导方式并返回 JSON（不要 markdown 代码块）：
{{
  "mode": "concept_check|analogy_guide|counter_example|deep_probe",
  "goal": "本轮对话目标",
  "expected_understanding": "预期帮助学生达到的理解层次",
  "rationale": "选择该模式的理由"
}}
"""

DIALOG_PROMPT = """\
你正在进行苏格拉底式对话。请针对学生的最新回答，提出下一个引导性问题。

对话模式：{mode}
对话目标：{goal}
学生最新回答：{student_response}
对话历史：{history}
知识参考：{knowledge}

记住：
- 只问一个问题
- 不要直接给答案
- 根据学生回答的深度调整问题难度
- 如果学生回答正确但理解较浅，用 deep_probe 追问
- 如果学生回答有误，用 counter_example 或 concept_check 纠正
"""

REFLECT_PROMPT = """\
回顾这次苏格拉底式对话的整体过程，进行反思。

对话历史：
{history}
初始评估：{initial_assessment}
对话目标：{dialog_goal}

请返回 JSON（不要 markdown 代码块）：
{{
  "effectiveness": "高|中|低",
  "understanding_progress": "学生理解力的变化描述",
  "key_insights": ["对话中学生展现的关键洞察"],
  "remaining_gaps": ["仍需弥补的认知空白"],
  "next_steps": "建议的下一步学习方向"
}}
"""


class SocraticDialogCapability(BaseCapability):
    manifest = CapabilityManifest(
        name="socratic_dialog",
        description="苏格拉底式对话：通过提问引导学生自主思考，不给答案。",
        stages=["assess", "plan", "dialog", "reflect"],
        tools_used=["rag"],
        cli_aliases=["socratic", "sd"],
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        history = self._format_history(context.conversation_history)
        knowledge = self._format_knowledge(context.knowledge_bases, context.metadata)
        student_response = context.user_message

        # 1. Assess
        async with stream.stage("assess", source=self.manifest.name):
            await stream.observation("正在评估学生的理解程度...", source=self.manifest.name, stage="assess")
            assess_result = await self._llm_json(
                ASSESS_PROMPT.format(history=history, knowledge=knowledge),
                fallback={"level": "初学", "evidence": "缺乏足够信息", "misconceptions": [], "strengths": []},
            )
            await stream.thinking(
                f"评估结果：{assess_result.get('level', '未知')}。依据：{assess_result.get('evidence', '')}",
                source=self.manifest.name,
                stage="assess",
            )

        # 2. Plan
        async with stream.stage("plan", source=self.manifest.name):
            await stream.observation("正在制定对话策略...", source=self.manifest.name, stage="plan")
            plan_result = await self._llm_json(
                PLAN_PROMPT.format(
                    level=assess_result.get("level", "初学"),
                    misconceptions=assess_result.get("misconceptions", []),
                    strengths=assess_result.get("strengths", []),
                    history=history,
                ),
                fallback={"mode": "concept_check", "goal": "了解学生基础理解", "expected_understanding": "能够用自己的话描述概念", "rationale": "默认模式"},
            )
            await stream.thinking(
                f"策略：{plan_result.get('mode', 'concept_check')}。目标：{plan_result.get('goal', '')}",
                source=self.manifest.name,
                stage="plan",
            )

        # 3. Dialog
        async with stream.stage("dialog", source=self.manifest.name):
            dialog_raw = await self._llm_text(
                DIALOG_PROMPT.format(
                    mode=plan_result.get("mode", "concept_check"),
                    goal=plan_result.get("goal", ""),
                    student_response=student_response,
                    history=history,
                    knowledge=knowledge,
                )
            )

            # Try to parse structured response; fall back to raw text
            dialog_result = self._parse_json_safe(dialog_raw)
            question = dialog_result.get("question", dialog_raw) if isinstance(dialog_result, dict) else dialog_raw

            await stream.content(question, source=self.manifest.name, stage="dialog")

        # 4. Reflect (lightweight — store in metadata for next turn)
        async with stream.stage("reflect", source=self.manifest.name):
            reflect_result = await self._llm_json(
                REFLECT_PROMPT.format(
                    history=history,
                    initial_assessment=str(assess_result),
                    dialog_goal=plan_result.get("goal", ""),
                ),
                fallback={"effectiveness": "中", "understanding_progress": "无法判断", "key_insights": [], "remaining_gaps": [], "next_steps": "继续对话"},
            )
            await stream.observation(
                f"反思：效果{reflect_result.get('effectiveness', '中')}。{reflect_result.get('next_steps', '')}",
                source=self.manifest.name,
                stage="reflect",
            )

        await stream.result(
            {
                "response": question,
                "assessment": assess_result,
                "plan": plan_result,
                "reflection": reflect_result,
            },
            source=self.manifest.name,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_history(conversation_history: list[dict[str, Any]]) -> str:
        if not conversation_history:
            return "（无历史对话）"
        lines = []
        for msg in conversation_history[-20:]:  # last 20 turns
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
            lines.append(f"[{role}] {content}")
        return "\n".join(lines)

    @staticmethod
    def _format_knowledge(knowledge_bases: list[str], metadata: dict[str, Any]) -> str:
        kb_text = metadata.get("knowledge_context", "")
        if kb_text:
            return kb_text
        if knowledge_bases:
            return f"可用知识库：{', '.join(knowledge_bases)}"
        return "（无特定知识参考）"

    async def _llm_text(self, prompt: str) -> str:
        config = get_llm_config()
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        resp = await complete(
            messages=messages,
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
        )
        return resp.strip() if resp else ""

    async def _llm_json(self, prompt: str, fallback: dict | None = None) -> dict:
        raw = await self._llm_text(prompt)
        parsed = self._parse_json_safe(raw)
        if isinstance(parsed, dict):
            return parsed
        return fallback or {}

    @staticmethod
    def _parse_json_safe(text: str) -> dict | str:
        text = text.strip()
        # Strip markdown code fences
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.startswith("```")]
            text = "\n".join(lines).strip()
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return text
