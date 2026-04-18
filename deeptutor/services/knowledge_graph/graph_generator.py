"""Auto-generate knowledge graphs from educational content via LLM."""

from __future__ import annotations

import json
import logging

from deeptutor.services.knowledge_graph.graph_model import (
    KnowledgeEdge,
    KnowledgeGraph,
    KnowledgeNode,
    _gen_id,
)
from deeptutor.services.knowledge_graph.graph_store import load_graph, save_graph

logger = logging.getLogger(__name__)

LITERATURE_KEYWORDS = [
    "骆驼祥子", "名著", "小说", "人物", "红楼梦", "三国", "水浒", "西游记",
    "朝花夕拾", "呐喊", "彷徨", "故事新编", "围城", "平凡的世界",
]

LITERATURE_PROMPT = """你是一个文学分析专家。请从以下文本中提取人物关系图。

返回 JSON 格式：
{{
  "characters": [
    {{"id": "c1", "label": "人物名", "description": "角色描述", "type": "protagonist/antagonist/supporting", "group": "阵营/家族"}}
  ],
  "relationships": [
    {{"source_id": "c1", "target_id": "c2", "relation": "夫妻/师徒/父子/朋友/敌人/上下级/恋人", "description": "关系描述"}}
  ],
  "plot_events": [
    {{"id": "e1", "label": "事件名", "description": "事件描述", "characters": ["c1","c2"], "chapter": "章节"}}
  ]
}}

严格返回 JSON，不要其他文字。

文本：
{content}
"""

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


def _is_literature_content(kb_name: str, content: str) -> bool:
    """Heuristic to detect literature/novel content."""
    combined = (kb_name + content[:2000]).lower()
    return any(kw in combined for kw in LITERATURE_KEYWORDS)


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling code fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise


async def generate_literature_graph(content: str, kb_name: str) -> KnowledgeGraph:
    """Generate a character relationship graph from literature content."""
    from deeptutor.services.llm import complete

    prompt = LITERATURE_PROMPT.format(content=content[:8000])
    response = await complete(
        prompt, system_prompt="你是一个JSON生成器。只返回纯JSON，不要markdown代码块。"
    )

    data = _extract_json(response)

    nodes: list[KnowledgeNode] = []
    edges: list[KnowledgeEdge] = []
    id_map: dict[str, str] = {}  # original id → generated KnowledgeNode id

    # Characters → level=2 nodes
    for char in data.get("characters", []):
        node = KnowledgeNode(
            id=char.get("id", _gen_id()),
            label=char.get("label", ""),
            description=char.get("description", ""),
            level=2,
            metadata={
                "type": char.get("type", "supporting"),
                "group": char.get("group", ""),
                "graph_type": "literature",
            },
        )
        id_map[char.get("id", "")] = node.id
        nodes.append(node)

    # Plot events → level=3 nodes
    for event in data.get("plot_events", []):
        event_node = KnowledgeNode(
            id=event.get("id", _gen_id()),
            label=event.get("label", ""),
            description=event.get("description", ""),
            level=3,
            metadata={
                "chapter": event.get("chapter", ""),
                "graph_type": "literature",
            },
        )
        id_map[event.get("id", "")] = event_node.id
        nodes.append(event_node)
        # Connect event to its characters
        for char_id in event.get("characters", []):
            mapped = id_map.get(char_id)
            if mapped:
                edges.append(
                    KnowledgeEdge(
                        source_id=mapped,
                        target_id=event_node.id,
                        relation="involved_in",
                        weight=0.7,
                    )
                )

    # Relationships → edges with labels
    for rel in data.get("relationships", []):
        src = id_map.get(rel.get("source_id", ""))
        tgt = id_map.get(rel.get("target_id", ""))
        if src and tgt:
            edges.append(
                KnowledgeEdge(
                    source_id=src,
                    target_id=tgt,
                    relation=rel.get("relation", "related_to"),
                    weight=1.0,
                    metadata={"description": rel.get("description", "")},
                )
            )

    # Add a root node for the work
    root = KnowledgeNode(
        label=kb_name,
        description=f"文学作品：{kb_name}",
        level=0,
        metadata={"graph_type": "literature"},
    )
    nodes.insert(0, root)
    for n in nodes[1:]:
        if n.level == 2:
            edges.append(
                KnowledgeEdge(source_id=root.id, target_id=n.id, relation="contains", weight=0.5)
            )

    new_graph = KnowledgeGraph(nodes=nodes, edges=edges)

    existing = load_graph(kb_name)
    if existing:
        result = _merge_graphs(existing, new_graph)
    else:
        result = new_graph

    save_graph(result, kb_name)
    return result


async def generate_from_content(content: str, kb_name: str) -> KnowledgeGraph:
    """Generate (or incrementally update) a knowledge graph from content."""
    # Auto-detect literature content
    if _is_literature_content(kb_name, content):
        return await generate_literature_graph(content, kb_name)

    from deeptutor.services.llm import complete

    prompt = GENERATE_PROMPT.format(content=content[:8000])
    response = await complete(prompt, system_prompt="你是一个JSON生成器。只返回纯JSON，不要markdown代码块。")

    try:
        data = _extract_json(response)
    except (json.JSONDecodeError, ValueError):
        logger.warning("LLM returned invalid JSON for knowledge graph generation")
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
