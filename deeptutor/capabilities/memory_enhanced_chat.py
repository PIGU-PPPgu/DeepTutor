"""Memory-Enhanced Chat Capability with 3-layer memory system."""

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

# ── Memory structure defaults ──────────────────────────────────────────

EMPTY_MEMORY: dict[str, Any] = {
    "short_term": {
        "recent_turns": [],       # last 10 exchanges: [{q, a}]
        "active_topic": None,     # current knowledge point being discussed
        "confusion_points": [],   # student's immediate confusions
    },
    "medium_term": {
        "current_chapter": None,
        "chapter_progress": 0.0,   # 0.0 → 1.0
        "discussed_topics": [],    # knowledge points covered
        "mastered": [],            # concepts student grasped
        "struggling": [],          # concepts student struggles with
    },
    "long_term": {
        "book_progress": 0.0,
        "learning_preferences": {},  # e.g. prefers visual explanations
        "weak_areas": [],
        "milestones": [],           # [{title, timestamp}]
        "mastery_summary": {},      # chapter → mastery_level
    },
}

MAX_SHORT_TERM_TURNS = 10


def _init_memory(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return existing memory from metadata or fresh empty structure."""
    if "memory" in metadata and isinstance(metadata["memory"], dict):
        mem = metadata["memory"]
        # ensure all keys exist (forward-compat)
        for layer, defaults in EMPTY_MEMORY.items():
            if layer not in mem:
                mem[layer] = defaults
            else:
                for k, v in defaults.items():
                    mem[layer].setdefault(k, v if not isinstance(v, list) else [])
        return mem
    return json.loads(json.dumps(EMPTY_MEMORY))  # deep copy


# ── Capability ─────────────────────────────────────────────────────────

class MemoryEnhancedChatCapability(BaseCapability):
    manifest = CapabilityManifest(
        name="memory_chat",
        description="Chat with 3-layer memory: short-term context, medium-term chapter progress, long-term mastery tracking.",
        stages=["recall", "chat", "learn", "store"],
        tools_used=[],
        cli_aliases=["memory_chat", "mc"],
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        config = get_llm_config()
        memory = _init_memory(context.metadata)

        # ── Stage 1: recall ─────────────────────────────────────────
        async with stream.stage("recall", source=self.manifest.name):
            memory = await self._recall(memory, context, config, stream)

        # ── Stage 2: chat ───────────────────────────────────────────
        reply: str = ""
        async with stream.stage("chat", source=self.manifest.name):
            reply = await self._chat(memory, context, config, stream)

        # ── Stage 3: learn ──────────────────────────────────────────
        async with stream.stage("learn", source=self.manifest.name):
            memory = await self._learn(memory, context, reply, config, stream)

        # ── Stage 4: store ──────────────────────────────────────────
        async with stream.stage("store", source=self.manifest.name):
            context.metadata["memory"] = memory

    # ── recall ──────────────────────────────────────────────────────

    async def _recall(
        self,
        memory: dict[str, Any],
        context: UnifiedContext,
        config: Any,
        stream: StreamBus,
    ) -> dict[str, Any]:
        """Optionally enrich memory with a brief LLM summary of prior state."""
        summary = json.dumps(memory, ensure_ascii=False, indent=2)
        prompt = (
            "以下是一个学生的三层学习记忆状态。请简要总结关键信息（2-3句话），"
            "用于辅助后续对话。如果记忆为空，直接回复'新学生'。\n\n"
            f"记忆状态：\n{summary}"
        )
        try:
            recap = await complete(
                prompt=prompt,
                system_prompt="你是一个教育记忆助手。简洁回复。",
                model=config.model,
                api_key=config.api_key,
                base_url=config.base_url,
                temperature=0.3,
            )
            await stream.thinking(f"[记忆回顾] {recap}", source="recall")
        except Exception:
            logger.debug("recall summarization failed, using raw memory", exc_info=True)
        return memory

    # ── chat ────────────────────────────────────────────────────────

    async def _chat(
        self,
        memory: dict[str, Any],
        context: UnifiedContext,
        config: Any,
        stream: StreamBus,
    ) -> str:
        """Generate a memory-aware reply."""
        mem_prompt = _build_memory_prompt(memory)
        user_msg = context.user_message or ""

        system_prompt = (
            "你是一位有记忆的阅读家教。根据以下记忆信息，个性化地回答学生的问题。"
            "如果学生在某个知识点有困难，多给例子和引导。\n\n"
            f"【学习记忆】\n{mem_prompt}"
        )

        reply = await complete(
            prompt=user_msg,
            system_prompt=system_prompt,
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
            temperature=0.7,
        )
        await stream.thinking(reply, source="chat")
        return reply

    # ── learn ───────────────────────────────────────────────────────

    async def _learn(
        self,
        memory: dict[str, Any],
        context: UnifiedContext,
        reply: str,
        config: Any,
        stream: StreamBus,
    ) -> dict[str, Any]:
        """Extract learning insights from the exchange and update memory."""
        user_msg = context.user_message or ""

        # update short-term turns
        turns = memory["short_term"]["recent_turns"]
        turns.append({"q": user_msg, "a": reply})
        if len(turns) > MAX_SHORT_TERM_TURNS:
            memory["short_term"]["recent_turns"] = turns[-MAX_SHORT_TERM_TURNS:]

        # use LLM to extract learning state changes
        extraction_prompt = (
            "根据以下师生对话，提取学习状态变化。严格返回JSON（不要markdown代码块）：\n"
            "{\n"
            '  "active_topic": "正在讨论的知识点（string或null）",\n'
            '  "confusion_points": ["学生困惑点"],\n'
            '  "mastered": ["本轮掌握的概念"],\n'
            '  "struggling": ["本轮仍有困难的概念"],\n'
            '  "milestone": "里程碑描述（string或null，无里程碑则为null）"\n'
            "}\n\n"
            f"学生：{user_msg}\n老师：{reply}"
        )

        try:
            raw = await complete(
                prompt=extraction_prompt,
                system_prompt="你是一个教育分析助手。只返回JSON。",
                model=config.model,
                api_key=config.api_key,
                base_url=config.base_url,
                temperature=0.2,
            )
            # strip markdown fences if present
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            data = json.loads(raw)

            # merge into memory
            st = memory["short_term"]
            if data.get("active_topic"):
                st["active_topic"] = data["active_topic"]
            st["confusion_points"] = (st.get("confusion_points") or []) + data.get("confusion_points", [])

            mt = memory["medium_term"]
            for c in data.get("mastered", []):
                if c not in mt["mastered"]:
                    mt["mastered"].append(c)
                if c in mt.get("struggling", []):
                    mt["struggling"].remove(c)
            for s in data.get("struggling", []):
                if s not in mt["struggling"]:
                    mt["struggling"].append(s)

            if data.get("milestone"):
                import time
                memory["long_term"]["milestones"].append({
                    "title": data["milestone"],
                    "timestamp": int(time.time()),
                })

            await stream.thinking(
                f"[学习分析] 掌握: {data.get('mastered', [])} | 困难: {data.get('struggling', [])} | 话题: {data.get('active_topic')}",
                source="learn",
            )
        except Exception:
            logger.debug("learn extraction failed", exc_info=True)

        return memory


# ── Helpers ────────────────────────────────────────────────────────────

def _build_memory_prompt(memory: dict[str, Any]) -> str:
    """Format memory into a human-readable prompt section."""
    st = memory.get("short_term", {})
    mt = memory.get("medium_term", {})
    lt = memory.get("long_term", {})

    parts: list[str] = []

    recent = st.get("recent_turns", [])
    if recent:
        parts.append("【最近对话】")
        for t in recent[-3:]:  # show last 3 to keep prompt short
            parts.append(f"  学生: {t.get('q', '')[:80]}")
            parts.append(f"  老师: {t.get('a', '')[:80]}")

    if st.get("active_topic"):
        parts.append(f"当前话题: {st['active_topic']}")
    if st.get("confusion_points"):
        parts.append(f"学生困惑: {', '.join(st['confusion_points'][-5:])}")

    if mt.get("current_chapter"):
        parts.append(f"当前章节: {mt['current_chapter']}")
    if mt.get("mastered"):
        parts.append(f"已掌握: {', '.join(mt['mastered'][-10:])}")
    if mt.get("struggling"):
        parts.append(f"有困难: {', '.join(mt['struggling'][-10:])}")

    if lt.get("learning_preferences"):
        parts.append(f"学习偏好: {json.dumps(lt['learning_preferences'], ensure_ascii=False)}")
    if lt.get("weak_areas"):
        parts.append(f"薄弱领域: {', '.join(lt['weak_areas'])}")
    if lt.get("milestones"):
        parts.append(f"最近里程碑: {lt['milestones'][-1].get('title', '')}")

    return "\n".join(parts) if parts else "（暂无学习记忆）"
