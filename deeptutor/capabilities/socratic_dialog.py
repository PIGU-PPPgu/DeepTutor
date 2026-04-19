"""
Socratic Dialog Capability
==========================

苏格拉底式对话：不给答案，通过提问引导学生自己思考。

三种模式：
- concept_guided（概念引导）：帮助学生理解概念的本质
- problem_guided（解题引导）：引导学生一步步解题
- error_correction（纠错引导）：针对错误回答进行追问

Stages: assess → plan → dialog → reflect
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.services.llm import complete
from deeptutor.services.llm.config import get_llm_config


# ---------------------------------------------------------------------------
# Dialog modes
# ---------------------------------------------------------------------------

class DialogMode(str, Enum):
    CONCEPT_GUIDED = "concept_guided"       # 概念引导
    PROBLEM_GUIDED = "problem_guided"       # 解题引导
    ERROR_CORRECTION = "error_correction"   # 纠错引导


# ---------------------------------------------------------------------------
# System prompt — 七年级数学教学风格
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
你是"苏老师"，一位擅长苏格拉底式提问的初中数学老师，面向七年级学生。

## 铁律
1. **绝不直接给出答案或解题步骤**，每次只问一个问题
2. 学生说"不知道"时，换一个更简单的角度再问，不要放弃
3. 用学生熟悉的生活场景打比方（买东西、分东西、走路、温度等）
4. 语气亲切但不啰嗦，像一个有耐心的叔叔/阿姨在聊天
5. 用"嗯，你说得有道理，那……""哦？那我们再想想……"这样的过渡

## 判断学生错误的思路
- 概念混淆（比如把方程和不等式搞混）→ 问"这两个有什么区别？"
- 运算错误（比如负号丢了、移项没变号）→ 问"你确定这一步是对的吗？为什么？"
- 逻辑跳跃（跳过中间步骤）→ 问"等等，你是怎么从这步到那步的？"
- 完全不理解 → 回到最基础的问题，从生活例子开始

## 回复格式
你必须返回 JSON（不要 markdown 代码块）：
{
  "question": "你要问学生的问题",
  "reasoning": "内部推理：为什么问这个问题，判断学生的什么",
  "mode": "concept_check | analogy_guide | counter_example | deep_probe | step_hint",
  "knowledge_points": ["本次对话涉及的知识点"],
  "confidence": 0.0-1.0
}
"""

ANALYSIS_SYSTEM_PROMPT = """你是一位七年级数学教学分析助手。你的任务是分析学生理解、制定引导策略、复盘对话效果。

要求：
1. 允许直接做结构化分析，不要扮演苏格拉底老师提问
2. 严格返回 JSON
3. 结论要基于学生最新输入和历史对话
4. 不要输出教学寒暄，不要反问用户
"""

# ---------------------------------------------------------------------------
# Stage prompts
# ---------------------------------------------------------------------------

ASSESS_PROMPT = """\
分析以下对话，判断学生对知识点的理解程度。这是七年级数学课。

对话历史：
{history}

知识参考：
{knowledge}

返回 JSON（不要 markdown 代码块）：
{{
  "level": "未入门|初学|部分理解|基本掌握|深入理解",
  "evidence": "判断依据（引用学生原话）",
  "misconceptions": [
    {{"what": "误解内容", "root_knowledge_point": "对应的知识点"}}
  ],
  "strengths": ["学生展现的优势"],
  "suggested_mode": "concept_guided|problem_guided|error_correction",
  "knowledge_points": ["对话中涉及的知识点列表"]
}}

判断 suggested_mode 的规则：
- 学生概念不清、理解有偏差 → concept_guided
- 学生在解题过程中卡住 → problem_guided
- 学生给出了错误答案 → error_correction
"""

PLAN_PROMPT = """\
根据评估，制定苏格拉底式对话策略。

学生水平：{level}
发现的误解：{misconceptions}
学生优势：{strengths}
对话模式：{mode}
对话历史：{history}

返回 JSON（不要 markdown 代码块）：
{{
  "mode": "{mode}",
  "goal": "本轮对话的最终目标（学生应该自己领悟到什么）",
  "sub_goals": ["逐步引导的子目标，按顺序"],
  "opening_question": "第一个要问学生的问题",
  "expected_understanding": "预期帮助学生达到的理解层次",
  "knowledge_points": ["本轮对话涉及的知识点"]
}}

注意：opening_question 必须是一个具体的、可以直接问学生的问题，不要给任何提示。
"""

DIALOG_PROMPT_CONCEPT = """\
【概念引导模式】
学生正在学习一个数学概念。通过提问帮学生自己理解概念的本质。

当前目标：{goal}
子目标进度：{sub_goals}
学生最新回答：{student_response}
对话历史：{history}
知识参考：{knowledge}

策略：
- 如果学生回答正确但表述模糊 → 追问"你能用自己的话再说一遍吗？"
- 如果学生回答错误 → 问一个生活化的类比来纠正
- 如果学生回答正确且清晰 → 用 deep_probe 往深处问"为什么这个成立？"

只问一个问题，不要给答案。
"""

DIALOG_PROMPT_PROBLEM = """\
【解题引导模式】
学生正在做一道数学题。通过提问引导学生自己一步步解题。

当前目标：{goal}
子目标进度：{sub_goals}
学生最新回答：{student_response}
对话历史：{history}
知识参考：{knowledge}

策略：
- 如果学生卡住 → 问"你觉得第一步应该做什么？"或"题目给了哪些条件？"
- 如果学生走错方向 → 问"等等，你觉得这样做合理吗？为什么？"
- 如果学生跳步 → 问"你是怎么从上一步到这一步的？中间发生了什么？"
- 如果学生做对了 → 问"很好！你怎么想到的？还有别的做法吗？"

只问一个问题，不要给答案或提示解题步骤。
"""

DIALOG_PROMPT_ERROR = """\
【纠错引导模式】
学生给出了错误答案。通过提问帮助学生自己发现并纠正错误。

当前目标：{goal}
发现的误解：{misconceptions}
学生最新回答：{student_response}
对话历史：{history}
知识参考：{knowledge}

策略：
- 先让学生自己验证："你算出来的答案对不对？有没有办法验证？"
- 用反例："如果按你这个答案，那……会怎样？"
- 引导回基本概念："这个公式的意思是什么？你用的对不对？"
- 不要说"你错了"，而是说"嗯，那我们再检查一下"

只问一个问题，不要直接指出错误在哪里。
"""

REFLECT_PROMPT = """\
回顾这次苏格拉底式对话，总结反思。

对话历史：
{history}
初始评估：{initial_assessment}
对话目标：{dialog_goal}

返回 JSON（不要 markdown 代码块）：
{{
  "effectiveness": "高|中|低",
  "understanding_progress": "学生理解力的变化",
  "key_insights": ["对话中学生展现的关键洞察或转折点"],
  "remaining_gaps": ["仍需弥补的认知空白"],
  "next_steps": "建议的下一步",
  "knowledge_points_discussed": ["本次对话讨论到的所有知识点"]
}}
"""


class SocraticDialogCapability(BaseCapability):
    manifest = CapabilityManifest(
        name="socratic_dialog",
        description="苏格拉底式对话：通过提问引导学生自主思考，不给答案。支持概念引导、解题引导、纠错引导三种模式。",
        stages=["assess", "plan", "dialog", "reflect"],
        tools_used=["rag"],
        cli_aliases=["socratic", "sd"],
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        history = self._format_history(context.conversation_history)
        knowledge = self._format_knowledge(context.knowledge_bases, context.metadata)
        student_response = context.user_message

        # Allow caller to force a mode via metadata
        forced_mode = context.metadata.get("dialog_mode")

        # ---- Stage 1: Assess ----
        async with stream.stage("assess", source=self.manifest.name):
            await stream.observation("正在评估你的理解程度…", source=self.manifest.name, stage="assess")
            assess_result = await self._llm_json(
                ASSESS_PROMPT.format(
                    history=f"[学生最新输入] {student_response}\n\n{history}" if history == "（无历史对话）" else f"[学生最新输入] {student_response}\n\n{history}",
                    knowledge=knowledge,
                ),
                fallback={
                    "level": "初学", "evidence": "缺乏足够信息",
                    "misconceptions": [], "strengths": [],
                    "suggested_mode": "concept_guided",
                    "knowledge_points": [],
                },
            )
            await stream.thinking(
                f"评估：{assess_result.get('level', '未知')} | "
                f"误解：{assess_result.get('misconceptions', [])} | "
                f"建议模式：{assess_result.get('suggested_mode', 'concept_guided')}",
                source=self.manifest.name,
                stage="assess",
            )

        # Determine dialog mode
        dialog_mode = forced_mode or assess_result.get("suggested_mode", "concept_guided")
        dialog_mode = self._validate_mode(dialog_mode)

        # ---- Stage 2: Plan ----
        async with stream.stage("plan", source=self.manifest.name):
            await stream.observation("正在设计引导策略…", source=self.manifest.name, stage="plan")
            plan_result = await self._llm_json(
                PLAN_PROMPT.format(
                    level=assess_result.get("level", "初学"),
                    misconceptions=assess_result.get("misconceptions", []),
                    strengths=assess_result.get("strengths", []),
                    mode=dialog_mode,
                    history=history,
                ),
                fallback={
                    "mode": dialog_mode,
                    "goal": "了解学生基础理解",
                    "sub_goals": [],
                    "opening_question": "你对这个知识点有什么了解？",
                    "expected_understanding": "能用自己话描述概念",
                    "knowledge_points": [],
                },
            )
            await stream.thinking(
                f"模式：{plan_result.get('mode', dialog_mode)} | "
                f"目标：{plan_result.get('goal', '')} | "
                f"子目标：{plan_result.get('sub_goals', [])}",
                source=self.manifest.name,
                stage="plan",
            )

        # ---- Stage 3: Dialog ----
        async with stream.stage("dialog", source=self.manifest.name):
            dialog_prompt = self._get_dialog_prompt(dialog_mode).format(
                goal=plan_result.get("goal", ""),
                sub_goals=plan_result.get("sub_goals", []),
                misconceptions=assess_result.get("misconceptions", []),
                student_response=student_response,
                history=history,
                knowledge=knowledge,
            )
            dialog_raw = await self._llm_text(dialog_prompt)

            dialog_result = self._parse_json_safe(dialog_raw)
            if isinstance(dialog_result, dict):
                question = dialog_result.get("question", dialog_raw)
                turn_kps = dialog_result.get("knowledge_points", [])
            else:
                question = dialog_raw
                turn_kps = []

            await stream.content(question, source=self.manifest.name, stage="dialog")

        # ---- Stage 4: Reflect ----
        async with stream.stage("reflect", source=self.manifest.name):
            reflect_result = await self._llm_json(
                REFLECT_PROMPT.format(
                    history=history,
                    initial_assessment=str(assess_result),
                    dialog_goal=plan_result.get("goal", ""),
                ),
                fallback={
                    "effectiveness": "中", "understanding_progress": "无法判断",
                    "key_insights": [], "remaining_gaps": [],
                    "next_steps": "继续对话",
                    "knowledge_points_discussed": [],
                },
            )
            await stream.observation(
                f"对话效果：{reflect_result.get('effectiveness', '中')}。{reflect_result.get('next_steps', '')}",
                source=self.manifest.name,
                stage="reflect",
            )

        # Collect all knowledge points
        all_kps = list(set(
            assess_result.get("knowledge_points", [])
            + plan_result.get("knowledge_points", [])
            + turn_kps
            + reflect_result.get("knowledge_points_discussed", [])
        ))

        await stream.result(
            {
                "response": question,
                "assessment": assess_result,
                "plan": plan_result,
                "reflection": reflect_result,
                "dialog_mode": dialog_mode,
                "knowledge_points": all_kps,
            },
            source=self.manifest.name,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_mode(mode: str) -> str:
        valid = {m.value for m in DialogMode}
        return mode if mode in valid else DialogMode.CONCEPT_GUIDED.value

    @staticmethod
    def _get_dialog_prompt(mode: str) -> str:
        prompts = {
            DialogMode.CONCEPT_GUIDED.value: DIALOG_PROMPT_CONCEPT,
            DialogMode.PROBLEM_GUIDED.value: DIALOG_PROMPT_PROBLEM,
            DialogMode.ERROR_CORRECTION.value: DIALOG_PROMPT_ERROR,
        }
        return prompts.get(mode, DIALOG_PROMPT_CONCEPT)

    @staticmethod
    def _format_history(conversation_history: list[dict[str, Any]]) -> str:
        if not conversation_history:
            return "（无历史对话）"
        lines = []
        for msg in conversation_history[-20:]:
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

    async def _llm_text(self, prompt: str, system_prompt: str = SYSTEM_PROMPT) -> str:
        config = get_llm_config()
        resp = await complete(
            prompt=prompt,
            system_prompt=system_prompt,
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
            temperature=0.7,
        )
        return resp.strip() if resp else ""

    async def _llm_json(
        self,
        prompt: str,
        fallback: dict | None = None,
        *,
        system_prompt: str = ANALYSIS_SYSTEM_PROMPT,
    ) -> dict:
        raw = await self._llm_text(prompt, system_prompt=system_prompt)
        parsed = self._parse_json_safe(raw)
        if isinstance(parsed, dict):
            return parsed
        return fallback or {}

    @staticmethod
    def _parse_json_safe(text: str) -> dict | str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.startswith("```")]
            text = "\n".join(lines).strip()
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return text
