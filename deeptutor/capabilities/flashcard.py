"""Flashcard generation with spaced repetition."""

from __future__ import annotations

import json
import re
from datetime import timedelta

from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.services.llm import complete
from deeptutor.services.llm.config import get_llm_config

_EBINGHAUS_INTERVALS = [1, 2, 4, 7, 15, 30]

_SYSTEM_PROMPT = """\
你是一位专业的教学设计专家，擅长从学习内容中提取知识点并制作闪卡。

根据用户提供的学科和内容，提取可记忆的知识点，生成闪卡。

输出严格的 JSON 格式（不要包含 markdown 代码块标记）：
{
  "cards": [
    {
      "id": 1,
      "type": "concept|formula|true_false|fill_blank",
      "front": "正面问题或术语",
      "back": "背面答案或定义",
      "tags": ["学科", "章节", "标签"],
      "difficulty": "easy|medium|hard"
    }
  ]
}

闪卡类型说明：
- concept: 概念卡（术语→定义）
- formula: 公式卡（公式名称→公式+适用条件）
- true_false: 判断卡（陈述→对/错+原因）
- fill_blank: 填空卡（带___的句子→答案）

每个知识点生成一张闪卡，数量根据内容自然决定（通常 5-15 张）。"""


def _parse_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown fences."""
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    body = m.group(1) if m else text
    return json.loads(body.strip())


def _build_schedule(cards: list[dict]) -> dict[str, list[int]]:
    """Generate Ebbinghaus spaced repetition schedule."""
    card_ids = [c["id"] for c in cards]
    schedule: dict[str, list[int]] = {}
    for day in _EBINGHAUS_INTERVALS:
        # Review all cards at each interval
        schedule[str(day)] = card_ids
    return schedule


class FlashcardCapability(BaseCapability):
    manifest = CapabilityManifest(
        name="flashcard",
        description="自动闪卡生成与间隔重复记忆计划。",
        stages=["extract", "generate", "schedule"],
        tools_used=[],
        cli_aliases=["flashcard"],
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        config = get_llm_config()
        user_content = context.user_message or context.get("content", "")
        subject = context.metadata.get("subject", "通用")
        chapter = context.metadata.get("chapter", "")

        # Stage 1 & 2: extract + generate (single LLM call)
        async with stream.stage("extract", source=self.manifest.name):
            prompt = f"学科：{subject}\n章节：{chapter}\n\n内容：\n{user_content}"
            raw = await complete(
                prompt=prompt,
                system_prompt=_SYSTEM_PROMPT,
                model=config.model,
                api_key=config.api_key,
                base_url=config.base_url,
                temperature=0.5,
            )
            data = _parse_json(raw)
            cards = data.get("cards", [])

            # Ensure each card has an id
            for i, card in enumerate(cards, 1):
                card.setdefault("id", i)

            await stream.thinking(
                "cards_generated",
                {"cards": cards, "count": len(cards)},
                source=self.manifest.name,
            )

        # Stage 3: schedule
        async with stream.stage("schedule", source=self.manifest.name):
            schedule = _build_schedule(cards)
            result = {
                "cards": cards,
                "review_schedule": schedule,
                "intervals_days": _EBINGHAUS_INTERVALS,
            }
            # Format cards as readable content
            lines = ["## 闪卡生成结果\n"]
            for card in cards:
                lines.append(f"**{card.get('front', card.get('question', ''))}** → {card.get('back', card.get('answer', ''))}")
            lines.append(f"\n📋 共 {len(cards)} 张闪卡，复习周期：{schedule}")
            await stream.content("\n".join(lines), source=self.manifest.name)
