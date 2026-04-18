"""Knowledge Graph capability — extract, build, query, and visualize knowledge graphs."""

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus

logger = logging.getLogger(__name__)

# ── Relation types ──────────────────────────────────────────────────────────

VALID_RELATIONS = {
    "contains": "包含",
    "belongs_to": "属于",
    "prerequisite_of": "前置知识",
    "related_to": "相关",
    "contrasts_with": "对比",
    "applied_in": "应用于",
    "derives_to": "推导出",
}

# ── Data structures ─────────────────────────────────────────────────────────


@dataclass
class GraphNode:
    id: str
    label: str
    type: str = "concept"
    description: str = ""
    difficulty: int = 0  # 1-5

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "description": self.description,
            "difficulty": self.difficulty,
        }


@dataclass
class GraphEdge:
    source: str
    target: str
    relation: str
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "weight": self.weight,
        }


class KnowledgeGraph:
    """In-memory knowledge graph with JSON serialization."""

    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self._adj: dict[str, list[tuple[str, GraphEdge]]] = defaultdict(list)
        self._radj: dict[str, list[tuple[str, GraphEdge]]] = defaultdict(list)

    # ── Build ───────────────────────────────────────────────────────────

    def add_node(self, node: GraphNode) -> None:
        if node.id in self.nodes:
            existing = self.nodes[node.id]
            if node.description:
                existing.description = node.description or existing.description
            if node.difficulty:
                existing.difficulty = node.difficulty or existing.difficulty
            return
        self.nodes[node.id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        # Check for duplicate
        for e in self.edges:
            if e.source == edge.source and e.target == edge.target and e.relation == edge.relation:
                return
        self.edges.append(edge)
        self._adj[edge.source].append((edge.target, edge))
        self._radj[edge.target].append((edge.source, edge))

    def add_triple(self, subject: str, relation: str, obj: str,
                   subject_desc: str = "", obj_desc: str = "",
                   difficulty: int = 0) -> None:
        s_id = self._make_id(subject)
        o_id = self._make_id(obj)
        self.add_node(GraphNode(id=s_id, label=subject, description=subject_desc, difficulty=difficulty))
        self.add_node(GraphNode(id=o_id, label=obj, description=obj_desc, difficulty=difficulty))
        self.add_edge(GraphEdge(source=s_id, target=o_id, relation=relation))

    @staticmethod
    def _make_id(label: str) -> str:
        return label.strip().lower()

    # ── Query ───────────────────────────────────────────────────────────

    def get_relations(self, label: str) -> list[GraphEdge]:
        """All edges touching a node."""
        nid = self._make_id(label)
        out = [e for _, e in self._adj.get(nid, [])]
        inn = [e for _, e in self._radj.get(nid, [])]
        return out + inn

    def prerequisite_chain(self, label: str) -> list[str]:
        """Follow prerequisite_of edges backwards to find all prerequisites."""
        nid = self._make_id(label)
        visited: set[str] = set()
        result: list[str] = []
        queue = deque([nid])
        while queue:
            cur = queue.popleft()
            if cur in visited:
                continue
            visited.add(cur)
            if cur != nid:
                node = self.nodes.get(cur)
                result.append(node.label if node else cur)
            for src, edge in self._radj.get(cur, []):
                if edge.relation == "prerequisite_of" and src not in visited:
                    queue.append(src)
        return result

    def shortest_path(self, label_a: str, label_b: str) -> list[str] | None:
        """BFS shortest path between two nodes, returns labels."""
        a_id = self._make_id(label_a)
        b_id = self._make_id(label_b)
        if a_id not in self.nodes or b_id not in self.nodes:
            return None
        visited = {a_id}
        queue = deque([(a_id, [a_id])])
        while queue:
            cur, path = queue.popleft()
            if cur == b_id:
                return [self.nodes[nid].label for nid in path]
            for nxt, _ in self._adj.get(cur, []):
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, path + [nxt]))
            for nxt, _ in self._radj.get(cur, []):
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, path + [nxt]))
        return None

    # ── Visualize ───────────────────────────────────────────────────────

    def to_mermaid(self) -> str:
        """Generate Mermaid graph with relation-specific line styles."""
        if not self.nodes:
            return "graph LR\n  empty[空图谱]"

        lines = ["graph LR"]

        # Different line styles per relation
        style_map = {
            "contains": "-->",
            "belongs_to": "-->",
            "prerequisite_of": "-->|前置|",
            "related_to": "-.->",
            "contrasts_with": "==>|对比|",
            "applied_in": "-->|应用|",
            "derives_to": "-->|推导|",
        }

        seen_edges = set()
        for edge in self.edges:
            s = self.nodes.get(edge.source)
            t = self.nodes.get(edge.target)
            if not s or not t:
                continue
            key = (edge.source, edge.target, edge.relation)
            if key in seen_edges:
                continue
            seen_edges.add(key)

            arrow = style_map.get(edge.relation, "-->")
            # Mermaid-safe labels
            sl = s.label.replace('"', "'")
            tl = t.label.replace('"', "'")
            lines.append(f'  {edge.source}["{sl}"] {arrow} {edge.target}["{tl}"]')

        return "\n".join(lines)

    def to_markdown_outline(self) -> str:
        """Markdown outline based on contains/belongs_to hierarchy."""
        children: dict[str, list[str]] = defaultdict(list)
        for edge in self.edges:
            if edge.relation in ("contains", "belongs_to"):
                children[edge.source].append(edge.target)

        roots = [nid for nid in self.nodes if not any(
            e.target == nid and e.relation in ("contains", "belongs_to")
            for e in self.edges
        )]

        if not roots:
            roots = list(self.nodes.keys())[:1]

        lines: list[str] = []
        visited: set[str] = set()

        def walk(nid: str, depth: int) -> None:
            if nid in visited or nid not in self.nodes:
                return
            visited.add(nid)
            node = self.nodes[nid]
            indent = "  " * depth
            lines.append(f"{indent}- **{node.label}**")
            if node.description:
                lines.append(f"{indent}  _{node.description}_")
            for child in children.get(nid, []):
                walk(child, depth + 1)

        for root in roots:
            walk(root, 0)

        return "\n".join(lines) if lines else "（空图谱）"

    # ── Serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KnowledgeGraph:
        g = cls()
        for nd in data.get("nodes", []):
            g.add_node(GraphNode(**nd))
        for ed in data.get("edges", []):
            g.add_edge(GraphEdge(**ed))
        return g


# ── LLM extraction prompt ───────────────────────────────────────────────────

EXTRACT_SYSTEM_PROMPT = """你是一个教育知识图谱提取引擎。从给定内容中提取知识实体和关系三元组。

## 关系类型（只用这些）：
- contains: A包含B（整体与部分）
- belongs_to: A属于B（分类归属）
- prerequisite_of: A是B的前置知识（学B之前需要先学A）
- related_to: A与B相关
- contrasts_with: A与B形成对比
- applied_in: A应用于B
- derives_to: A可以推导出B

## 输出格式（严格JSON）
```json
{
  "triples": [
    {
      "subject": "实体名",
      "relation": "关系类型",
      "object": "实体名",
      "subject_description": "简短描述（可选）",
      "object_description": "简短描述（可选）",
      "difficulty": 3
    }
  ]
}
```

只输出JSON，不要输出其他内容。每条内容至少提取3个三元组。"""


class KnowledgeGraphCapability(BaseCapability):
    manifest = CapabilityManifest(
        name="knowledge_graph",
        description="Extract, build, query, and visualize knowledge graphs from educational content.",
        stages=["extract", "build", "query", "visualize"],
        tools_used=[],
        cli_aliases=["kg", "knowledge_graph"],
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        content = context.user_message or ""
        if not content.strip():
            async with stream.stage("respond", source=self.manifest.name):
                await stream.thinking("请提供内容以构建知识图谱。", source=self.manifest.name)
            return

        graph = KnowledgeGraph()

        async with stream.stage("extract", source=self.manifest.name):
            triples = await self._extract_triples(content)
            await stream.thinking(f"提取到 {len(triples)} 个三元组", source=self.manifest.name)

        async with stream.stage("build", source=self.manifest.name):
            for t in triples:
                graph.add_triple(
                    subject=t["subject"],
                    relation=t["relation"],
                    obj=t["object"],
                    subject_desc=t.get("subject_description", ""),
                    obj_desc=t.get("object_description", ""),
                    difficulty=t.get("difficulty", 0),
                )
            await stream.thinking(f"构建图谱：{len(graph.nodes)} 个节点，{len(graph.edges)} 条边", source=self.manifest.name)

        async with stream.stage("visualize", source=self.manifest.name):
            mermaid = graph.to_mermaid()
            outline = graph.to_markdown_outline()
            await stream.result(f"## 知识图谱大纲\n\n{outline}\n\n## Mermaid 图\n\n{mermaid}", source=self.manifest.name)

    async def _extract_triples(self, content: str) -> list[dict[str, Any]]:
        from deeptutor.services.llm import complete
        from deeptutor.services.llm.config import get_llm_config

        config = get_llm_config()
        response = await complete(
            prompt=f"请从以下内容中提取知识图谱三元组：\n\n{content[:3000]}",
            system_prompt=EXTRACT_SYSTEM_PROMPT,
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
            temperature=0.3,
        )
        return self._parse_triples(response)

    @staticmethod
    def _parse_triples(text: str) -> list[dict[str, Any]]:
        """Parse JSON from LLM response, tolerating markdown fences."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        try:
            data = json.loads(text)
            return data.get("triples", [])
        except json.JSONDecodeError:
            logger.warning("Failed to parse triples JSON from LLM")
            return []
