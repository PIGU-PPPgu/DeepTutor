"""Mindmap capability — extract knowledge structure and render as mind maps."""

from __future__ import annotations

import json
from typing import Any

from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.services.llm import complete
from deeptutor.services.llm.config import get_llm_config

# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------

EXTRACT_PROMPT = """\
分析以下内容，提取知识结构。返回严格 JSON（不要 markdown 代码块）：

{
  "root": "主题名称",
  "nodes": [
    {
      "id": "A",
      "name": "概念1",
      "parent": null,
      "children": ["B", "C"],
      "relations": [{"target": "D", "type": "因果|对比|相关"}]
    }
  ]
}

内容：
{text}"""

STRUCTURE_PROMPT = """\
将以下节点列表组织为 {map_type} 类型的树形结构。返回严格 JSON（不要 markdown 代码块）：

{
  "name": "根节点",
  "children": [
    {"name": "子节点1", "children": [...]},
    {"name": "子节点2", "children": [...]}
  ]
}

map_type 可选：knowledge_structure（知识结构图）、concept_relation（概念关系图）、timeline（时间线图）
当前 map_type: {map_type}

节点数据：
{nodes_json}"""

# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _tree_to_mermaid(node: dict, parent_id: str = "A", counter: list | None = None) -> str:
    """Convert a tree dict to Mermaid graph TD lines."""
    if counter is None:
        counter = [0]
    lines: list[str] = []
    name = node.get("name", "?")
    my_id = parent_id

    children = node.get("children", [])
    for i, child in enumerate(children):
        counter[0] += 1
        child_id = f"N{counter[0]}"
        child_name = child.get("name", "?")
        lines.append(f"  {my_id}[\"{name}\"] --> {child_id}[\"{child_name}\"]")
        lines.append(_tree_to_mermaid(child, child_id, counter))

    return "\n".join(lines)


def _tree_to_markdown(node: dict, level: int = 1) -> str:
    """Convert tree to markdown nested headings."""
    prefix = "#" * min(level, 6)
    lines = [f"{prefix} {node.get('name', '?')}"]
    for child in node.get("children", []):
        lines.append(_tree_to_markdown(child, level + 1))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Capability
# ---------------------------------------------------------------------------


class MindmapCapability(BaseCapability):
    manifest = CapabilityManifest(
        name="mindmap",
        description="Generate mind maps from content: extract structure, render as Mermaid/Markdown/JSON.",
        stages=["extract", "structure", "render", "export"],
        tools_used=[],
        cli_aliases=["mindmap", "map"],
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        content = context.user_message
        map_type = context.metadata.get("map_type", "knowledge_structure")
        config = get_llm_config()

        # --- Stage 1: extract ---
        extracted: dict[str, Any] = {}
        async with stream.stage("extract", source=self.manifest.name):
            raw = await complete(
                prompt=EXTRACT_PROMPT.format(text=content[:6000]),
                system_prompt="你是知识结构分析专家，只返回 JSON。",
                model=config.model,
                api_key=config.api_key,
                base_url=config.base_url,
                temperature=0.3,
            )
            try:
                extracted = json.loads(raw.strip().strip("`"))
            except json.JSONDecodeError:
                extracted = {"root": "主题", "nodes": []}
            await stream.thinking(
                f"🧠 提取完成：根节点='{extracted.get('root', '?')}'，"
                f"共 {len(extracted.get('nodes', []))} 个节点",
                source=self.manifest.name,
            )

        # --- Stage 2: structure ---
        tree: dict[str, Any] = {}
        async with stream.stage("structure", source=self.manifest.name):
            raw = await complete(
                prompt=STRUCTURE_PROMPT.format(
                    map_type=map_type,
                    nodes_json=json.dumps(extracted.get("nodes", []), ensure_ascii=False),
                ),
                system_prompt="你是知识结构专家，只返回 JSON 树形结构。",
                model=config.model,
                api_key=config.api_key,
                base_url=config.base_url,
                temperature=0.3,
            )
            try:
                tree = json.loads(raw.strip().strip("`"))
            except json.JSONDecodeError:
                tree = {"name": extracted.get("root", "主题"), "children": []}
            await stream.thinking(
                f"🏗️ 结构构建完成：类型={map_type}",
                source=self.manifest.name,
            )

        # --- Stage 3: render ---
        result: dict[str, Any] = {}
        async with stream.stage("render", source=self.manifest.name):
            mermaid_body = _tree_to_mermaid(tree)
            mermaid = f"graph TD\n{mermaid_body}" if mermaid_body else f"graph TD\n  A[\"{tree.get('name', '?')}\"]"
            markdown = _tree_to_markdown(tree)
            result = {
                "root": tree.get("name", extracted.get("root", "主题")),
                "type": map_type,
                "mermaid": mermaid,
                "markdown": markdown,
                "tree": tree,
            }
            await stream.thinking(
                f"🎨 渲染完成：Mermaid {len(mermaid)} chars, Markdown {len(markdown)} chars",
                source=self.manifest.name,
            )

        # --- Stage 4: export ---
        async with stream.stage("export", source=self.manifest.name):
            # Store result in context metadata for downstream use
            context.metadata["mindmap_result"] = result
            await stream.content(
                f"## 思维导图\n\n{markdown}",
                source=self.manifest.name,
            )
            await stream.thinking(
                f"📤 导出就绪：Mermaid / Markdown / JSON 三种格式",
                source=self.manifest.name,
            )
