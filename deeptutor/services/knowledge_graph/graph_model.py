"""Data models for the Knowledge Graph system."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


def _gen_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class KnowledgeNode:
    id: str = field(default_factory=_gen_id)
    label: str = ""
    description: str = ""
    parent_id: str | None = None
    level: int = 0  # 0=学科, 1=章节, 2=知识点, 3=考点
    mastery: float = 0.0  # 0.0-1.0
    source: str = "textbook"  # textbook / chat / quiz
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "parent_id": self.parent_id,
            "level": self.level,
            "mastery": self.mastery,
            "source": self.source,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> KnowledgeNode:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class KnowledgeEdge:
    source_id: str = ""
    target_id: str = ""
    relation: str = "related_to"  # prerequisite / contains / related_to / derived_from
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation,
            "weight": self.weight,
        }
        if self.metadata:
            d["metadata"] = self.metadata
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> KnowledgeEdge:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class KnowledgeGraph:
    nodes: list[KnowledgeNode] = field(default_factory=list)
    edges: list[KnowledgeEdge] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> KnowledgeGraph:
        return cls(
            nodes=[KnowledgeNode.from_dict(n) for n in d.get("nodes", [])],
            edges=[KnowledgeEdge.from_dict(e) for e in d.get("edges", [])],
        )

    def get_node(self, node_id: str) -> KnowledgeNode | None:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def get_children(self, parent_id: str) -> list[KnowledgeNode]:
        return [n for n in self.nodes if n.parent_id == parent_id]

    def get_weak_nodes(self, threshold: float = 0.3) -> list[KnowledgeNode]:
        return [n for n in self.nodes if n.mastery > 0 and n.mastery < threshold]

    def stats(self) -> dict[str, Any]:
        total = len(self.nodes)
        if total == 0:
            return {"total": 0, "mastered": 0, "learning": 0, "unstudied": 0, "weak": 0, "mastery_avg": 0.0}
        mastered = sum(1 for n in self.nodes if n.mastery >= 0.8)
        learning = sum(1 for n in self.nodes if 0.3 <= n.mastery < 0.8)
        weak = sum(1 for n in self.nodes if 0 < n.mastery < 0.3)
        unstudied = sum(1 for n in self.nodes if n.mastery == 0)
        mastery_avg = sum(n.mastery for n in self.nodes) / total
        return {
            "total": total,
            "mastered": mastered,
            "learning": learning,
            "unstudied": unstudied,
            "weak": weak,
            "mastery_avg": round(mastery_avg, 3),
        }
