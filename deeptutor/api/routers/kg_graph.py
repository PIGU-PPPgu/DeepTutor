"""Knowledge Graph API Router — interactive graph system."""

from __future__ import annotations

import traceback

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from deeptutor.services.knowledge_graph.graph_store import list_graphs, load_graph
from deeptutor.services.knowledge_graph.mastery_tracker import QuizResult, update_from_chat, update_from_quiz

router = APIRouter()


# ---- Request / Response schemas ----

class GenerateRequest(BaseModel):
    content: str

class MasteryUpdate(BaseModel):
    mastery: float
    source: str | None = None

class ChatMasteryUpdate(BaseModel):
    node_id: str
    correct: bool

class QuizMasteryUpdate(BaseModel):
    results: list[QuizResult]


# ---- Endpoints ----

@router.get("/knowledge-graph")
async def list_all_graphs():
    """List all saved knowledge graph names."""
    return {"graphs": list_graphs()}


@router.get("/knowledge-graph/{kb_name}")
async def get_graph(kb_name: str):
    """Get the full knowledge graph for a knowledge base."""
    graph = load_graph(kb_name)
    if not graph:
        raise HTTPException(status_code=404, detail=f"Knowledge graph '{kb_name}' not found")
    return graph.to_dict()


@router.get("/knowledge-graph/{kb_name}/stats")
async def get_stats(kb_name: str):
    """Get statistics for a knowledge graph."""
    graph = load_graph(kb_name)
    if not graph:
        raise HTTPException(status_code=404, detail=f"Knowledge graph '{kb_name}' not found")
    return graph.stats()


@router.post("/knowledge-graph/{kb_name}/generate")
async def generate_graph(kb_name: str, req: GenerateRequest):
    """Generate or incrementally update a knowledge graph from content."""
    from deeptutor.services.knowledge_graph.graph_generator import generate_from_content
    try:
        graph = await generate_from_content(req.content, kb_name)
        return graph.to_dict()
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")


@router.patch("/knowledge-graph/{kb_name}/nodes/{node_id}")
async def update_node(kb_name: str, node_id: str, req: MasteryUpdate):
    """Update a node's mastery level."""
    from deeptutor.services.knowledge_graph.graph_store import save_graph
    graph = load_graph(kb_name)
    if not graph:
        raise HTTPException(status_code=404, detail=f"Graph '{kb_name}' not found")
    node = graph.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    node.mastery = max(0.0, min(1.0, req.mastery))
    if req.source:
        node.source = req.source
    save_graph(graph, kb_name)
    return node.to_dict()


@router.get("/knowledge-graph/{kb_name}/weak")
async def get_weak_nodes(kb_name: str, threshold: float = 0.3):
    """Get weak knowledge points (mastery > 0 but < threshold)."""
    graph = load_graph(kb_name)
    if not graph:
        raise HTTPException(status_code=404, detail=f"Graph '{kb_name}' not found")
    weak = graph.get_weak_nodes(threshold)
    return {"nodes": [n.to_dict() for n in weak]}


@router.post("/knowledge-graph/{kb_name}/mastery/chat")
async def mastery_from_chat(kb_name: str, req: ChatMasteryUpdate):
    """Update mastery from a chat interaction."""
    result = update_from_chat(req.node_id, req.correct, kb_name)
    if result is None:
        raise HTTPException(status_code=404, detail="Node or graph not found")
    return {"node_id": req.node_id, "mastery": result}


@router.post("/knowledge-graph/{kb_name}/mastery/quiz")
async def mastery_from_quiz(kb_name: str, req: QuizMasteryUpdate):
    """Batch update mastery from quiz results."""
    updated = update_from_quiz(req.results, kb_name)
    return {"updated": updated}
