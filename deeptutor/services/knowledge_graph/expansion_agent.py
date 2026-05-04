"""Knowledge Expansion Agent — recursively decompose knowledge nodes to exam-point granularity."""

from __future__ import annotations

import json
import logging

from deeptutor.services.knowledge_graph.graph_model import (
    KnowledgeEdge,
    KnowledgeGraph,
    KnowledgeNode,
)
from deeptutor.services.knowledge_graph.graph_generator import _extract_json
from deeptutor.services.knowledge_graph.graph_store import load_graph, save_graph

logger = logging.getLogger(__name__)


def _chunk(lst: list, n: int):
    """Split list into chunks of size n."""
    return [lst[i : i + n] for i in range(0, len(lst), n)]


class KnowledgeExpansionAgent:
    """Recursively decompose knowledge nodes until target granularity is reached."""

    def __init__(self, kb_name: str, max_depth: int = 5, target_nodes: int = 1500):
        self.kb_name = kb_name
        self.max_depth = max_depth
        self.target_nodes = target_nodes

    async def expand(self) -> KnowledgeGraph:
        """Load existing graph, find leaf nodes, and decompose layer by layer."""
        graph = load_graph(self.kb_name)
        if graph is None:
            graph = KnowledgeGraph()

        for depth in range(self.max_depth):
            if len(graph.nodes) >= self.target_nodes:
                logger.info("Target reached: %d nodes", len(graph.nodes))
                break

            # Leaf nodes = nodes that are nobody's parent, and level < 4
            parent_ids = {n.parent_id for n in graph.nodes if n.parent_id}
            leaves = [n for n in graph.nodes if n.id not in parent_ids and n.level < 4]

            if not leaves:
                logger.info("No more leaves to expand at depth %d", depth)
                break

            logger.info("Depth %d: expanding %d leaf nodes", depth, len(leaves))

            for batch in _chunk(leaves, 5):
                if len(graph.nodes) >= self.target_nodes:
                    break
                await self._expand_batch(graph, batch)
                save_graph(graph, self.kb_name)  # incremental save

        return graph

    async def _expand_batch(self, graph: KnowledgeGraph, nodes: list[KnowledgeNode]) -> None:
        """Use LLM to decompose a batch of leaf nodes."""
        contexts: list[str] = []
        for node in nodes:
            chain = self._get_ancestor_chain(graph, node)
            contexts.append(
                f"知识点「{node.label}」(层级{node.level})：{node.description}\n"
                f"上级链路：{' → '.join(chain)}"
            )

        prompt = f"""你是K12教育知识图谱专家。请将以下知识点进一步拆解为更细粒度的子知识点和考点。

拆解规则：
1. 每个知识点拆出 3-8 个子知识点
2. 子知识点类型：concept(概念)、formula(公式)、method(方法)、trap(易错点)、exam_point(考点)
3. 子知识点要具体到学生能直接用来做题的程度
4. 包含易错点和常见考法
5. 严格返回JSON格式

需要拆解的知识点：
{chr(10).join(contexts)}

返回格式（每个知识点一个数组）：
{{
  "expansions": [
    {{
      "parent_id": "原始节点ID",
      "children": [
        {{"label": "子知识点名", "description": "详细描述", "type": "concept/formula/method/trap/exam_point"}}
      ]
    }}
  ]
}}

只返回JSON，不要其他文字。"""

        try:
            from deeptutor.services.llm import complete

            response = await complete(prompt, system_prompt="你是JSON生成器。只返回纯JSON。", temperature=0.3)
        except Exception:
            logger.exception("LLM call failed during expansion")
            return

        try:
            data = _extract_json(response)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse expansion JSON: {e}")
            # Try smaller batch
            return

        for expansion in data.get("expansions", []):
            parent_id = expansion.get("parent_id", "")
            parent = graph.get_node(parent_id)
            if not parent:
                # Try fuzzy match by position (LLM may mangle IDs)
                continue

            existing_children = graph.get_children(parent_id)
            start_idx = len(existing_children)

            for i, child in enumerate(expansion.get("children", [])):
                new_id = f"{parent_id}.{start_idx + i}"
                child_type = child.get("type", "concept")
                new_node = KnowledgeNode(
                    id=new_id,
                    label=child["label"],
                    description=child.get("description", ""),
                    parent_id=parent_id,
                    level=parent.level + 1,
                    mastery=0.0,
                    source="expansion",
                    metadata={"type": child_type, "expanded_from": parent_id},
                )
                graph.nodes.append(new_node)
                graph.edges.append(
                    KnowledgeEdge(
                        source_id=parent_id,
                        target_id=new_id,
                        relation="contains",
                        weight=1.0,
                    )
                )

    @staticmethod
    def _get_ancestor_chain(graph: KnowledgeGraph, node: KnowledgeNode) -> list[str]:
        """Walk up parent chain and return labels from root to current node."""
        chain = [node.label]
        current = node
        while current.parent_id:
            parent = graph.get_node(current.parent_id)
            if not parent:
                break
            chain.append(parent.label)
            current = parent
        return list(reversed(chain))
