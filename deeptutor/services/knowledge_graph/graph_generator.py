"""Auto-generate knowledge graphs from educational content via LLM."""

from __future__ import annotations

import json
import logging

from deeptutor.services.knowledge_graph.graph_model import (
    KnowledgeEdge,
    KnowledgeGraph,
    KnowledgeNode,
)
from deeptutor.services.knowledge_graph.graph_store import load_graph, save_graph

logger = logging.getLogger(__name__)

GENERATE_PROMPT = """你是一个K12教育知识图谱提取专家。请从以下教学内容中提取结构化的知识图谱。

要求：
1. 分四个层级提取：学科(level=0) → 章节(level=1) → 知识点(level=2) → 考点(level=3)
2. 每个节点包含：label(名称), description(简短描述), level(层级), parent_id(父节点ID，顶级为null)
3. 提取节点间的关系边：prerequisite(前置知识), contains(包含), related_to(关联), derived_from(派生)
4. 严格返回以下JSON格式，不要添加任何其他文字：

{{"nodes": [{{"id": "n0", "label": "数学", "description": "初中数学", "level": 0, "parent_id": null}}], "edges": [{{"source_id": "n1", "target_id": "n2", "relation": "prerequisite", "weight": 0.9}}]}}

教学内容：
{content}
"""


def _merge_graphs(existing: KnowledgeGraph, new_graph: KnowledgeGraph) -> KnowledgeGraph:
    """Merge new graph into existing, deduplicating by label+level+parent_id."""
    existing_keys = {(n.label, n.level, n.parent_id) for n in existing.nodes}
    id_map: dict[str, str] = {}  # old_id → existing_id or new_id

    for node in new_graph.nodes:
        key = (node.label, node.level, node.parent_id)
        if key in existing_keys:
            # Map new id to existing node
            match = next(
                n for n in existing.nodes
                if n.label == node.label and n.level == node.level and n.parent_id == node.parent_id
            )
            id_map[node.id] = match.id
        else:
            id_map[node.id] = node.id
            existing.nodes.append(node)
            existing_keys.add(key)

    for edge in new_graph.edges:
        src = id_map.get(edge.source_id, edge.source_id)
        tgt = id_map.get(edge.target_id, edge.target_id)
        mapped = KnowledgeEdge(source_id=src, target_id=tgt, relation=edge.relation, weight=edge.weight)
        # Avoid duplicate edges
        dup = any(
            e.source_id == mapped.source_id and e.target_id == mapped.target_id and e.relation == mapped.relation
            for e in existing.edges
        )
        if not dup:
            existing.edges.append(mapped)

    return existing


async def generate_from_content(content: str, kb_name: str) -> KnowledgeGraph:
    """Generate (or incrementally update) a knowledge graph from content."""
    from deeptutor.services.llm import complete

    prompt = GENERATE_PROMPT.format(content=content[:8000])
    response = await complete(prompt, system_prompt="你是一个JSON生成器。只返回纯JSON，不要markdown代码块。")

    # Strip markdown code fences if present
    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("LLM returned invalid JSON for knowledge graph generation")
        # Try to extract JSON from response
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(text[start:end])
        else:
            return KnowledgeGraph()

    new_graph = KnowledgeGraph(
        nodes=[KnowledgeNode.from_dict(n) for n in data.get("nodes", [])],
        edges=[KnowledgeEdge.from_dict(e) for e in data.get("edges", [])],
    )

    existing = load_graph(kb_name)
    if existing:
        result = _merge_graphs(existing, new_graph)
    else:
        result = new_graph

    save_graph(result, kb_name)
    return result
