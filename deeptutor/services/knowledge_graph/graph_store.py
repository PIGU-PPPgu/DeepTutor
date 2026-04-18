"""JSON file-based persistence for knowledge graphs."""

from __future__ import annotations

import json
from pathlib import Path

from deeptutor.services.knowledge_graph.graph_model import KnowledgeGraph

# Default storage root — mirrors project's data/ pattern
_DEFAULT_ROOT = Path("data/user/workspace/knowledge_graphs")


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _graph_path(kb_name: str, root: Path | None = None) -> Path:
    base = root or _DEFAULT_ROOT
    return base / f"{kb_name}.json"


def save_graph(graph: KnowledgeGraph, kb_name: str, root: Path | None = None) -> Path:
    """Save graph to JSON file. Returns the path written."""
    p = _graph_path(kb_name, root)
    _ensure_dir(p)
    p.write_text(json.dumps(graph.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_graph(kb_name: str, root: Path | None = None) -> KnowledgeGraph | None:
    """Load graph from JSON. Returns None if not found."""
    p = _graph_path(kb_name, root)
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return KnowledgeGraph.from_dict(data)


def delete_graph(kb_name: str, root: Path | None = None) -> bool:
    p = _graph_path(kb_name, root)
    if p.exists():
        p.unlink()
        return True
    return False


def list_graphs(root: Path | None = None) -> list[str]:
    base = root or _DEFAULT_ROOT
    if not base.exists():
        return []
    return [p.stem for p in base.glob("*.json")]
