"""Knowledge Graph tool for function-calling in chat mode."""

from __future__ import annotations

import json
import logging
from typing import Any

from deeptutor.core.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult
from deeptutor.capabilities.knowledge_graph import KnowledgeGraph, KnowledgeGraphCapability

logger = logging.getLogger(__name__)


class KnowledgeGraphTool(BaseTool):
    """Tool wrapper for knowledge graph operations via function-calling."""

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="knowledge_graph",
            description=(
                "Build and query a knowledge graph from educational content. "
                "Actions: 'extract' (extract triples from text), "
                "'query' (find relations/path/prerequisites for a concept), "
                "'visualize' (render graph as Mermaid or outline)."
            ),
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description="Action: extract, query, visualize",
                    enum=["extract", "query", "visualize"],
                ),
                ToolParameter(
                    name="content",
                    type="string",
                    description="Content text to extract knowledge from (for 'extract' action).",
                    required=False,
                ),
                ToolParameter(
                    name="concept",
                    type="string",
                    description="Concept label to query (for 'query' action).",
                    required=False,
                ),
                ToolParameter(
                    name="target_concept",
                    type="string",
                    description="Second concept for path finding (optional).",
                    required=False,
                ),
                ToolParameter(
                    name="graph_json",
                    type="string",
                    description="Serialized graph JSON to query/visualize (from previous extract).",
                    required=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "extract")

        if action == "extract":
            return await self._do_extract(kwargs)
        elif action == "query":
            return self._do_query(kwargs)
        elif action == "visualize":
            return self._do_visualize(kwargs)
        else:
            return ToolResult(content=f"Unknown action: {action}", success=False)

    async def _do_extract(self, kwargs: dict) -> ToolResult:
        content = kwargs.get("content", "")
        if not content or len(content.strip()) < 10:
            return ToolResult(content="Content too short for extraction.", success=False)

        cap = KnowledgeGraphCapability()
        triples = await cap._extract_triples(content)
        if not triples:
            return ToolResult(content="未能提取到知识三元组。", success=False)

        graph = KnowledgeGraph()
        for t in triples:
            graph.add_triple(
                subject=t["subject"],
                relation=t["relation"],
                obj=t["object"],
                subject_desc=t.get("subject_description", ""),
                obj_desc=t.get("object_description", ""),
                difficulty=t.get("difficulty", 0),
            )

        graph_data = graph.to_dict()
        mermaid = graph.to_mermaid()
        return ToolResult(
            content=f"提取到 {len(triples)} 个三元组，{len(graph.nodes)} 个节点。\n\n{mermaid}",
            metadata={"graph": graph_data, "triple_count": len(triples)},
        )

    def _do_query(self, kwargs: dict) -> ToolResult:
        graph_json = kwargs.get("graph_json", "")
        concept = kwargs.get("concept", "")
        target = kwargs.get("target_concept", "")

        graph = self._load_graph(graph_json)
        if not graph or not graph.nodes:
            return ToolResult(content="No graph data provided. Run 'extract' first.", success=False)
        if not concept:
            return ToolResult(content="Provide a 'concept' to query.", success=False)

        parts: list[str] = []

        # Relations
        relations = graph.get_relations(concept)
        if relations:
            parts.append(f"### {concept} 的关联关系")
            for r in relations:
                s = graph.nodes.get(r.source)
                t = graph.nodes.get(r.target)
                parts.append(f"- {s.label if s else r.source} → [{r.relation}] → {t.label if t else r.target}")

        # Prerequisites
        prereqs = graph.prerequisite_chain(concept)
        if prereqs:
            parts.append(f"\n### {concept} 的前置知识链")
            parts.append(" → ".join(prereqs))

        # Path
        if target:
            path = graph.shortest_path(concept, target)
            if path:
                parts.append(f"\n### {concept} → {target} 最短路径")
                parts.append(" → ".join(path))
            else:
                parts.append(f"\n未找到 {concept} → {target} 的路径")

        return ToolResult(content="\n".join(parts) if parts else f"未找到与 {concept} 相关的信息。")

    def _do_visualize(self, kwargs: dict) -> ToolResult:
        graph_json = kwargs.get("graph_json", "")
        graph = self._load_graph(graph_json)
        if not graph or not graph.nodes:
            return ToolResult(content="No graph data provided.", success=False)

        mermaid = graph.to_mermaid()
        outline = graph.to_markdown_outline()
        return ToolResult(
            content=f"## 知识图谱大纲\n\n{outline}\n\n## Mermaid 图\n\n{mermaid}",
            metadata={"mermaid": mermaid, "outline": outline},
        )

    @staticmethod
    def _load_graph(graph_json: str) -> KnowledgeGraph | None:
        if not graph_json:
            return None
        try:
            data = json.loads(graph_json)
            return KnowledgeGraph.from_dict(data)
        except (json.JSONDecodeError, Exception):
            return None
