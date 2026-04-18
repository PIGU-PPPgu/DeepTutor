"""Learning Plan API Router — personalized study plans based on knowledge graph mastery."""

from __future__ import annotations

import traceback

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from deeptutor.capabilities.learning_guide import generate_plan, get_cached_plan, save_plan

router = APIRouter()


# ---- Schemas ----

class PlanResponse(BaseModel):
    kb_name: str
    total_weak_points: int
    estimated_days: int
    daily_plans: list[dict]
    generated_at: str | None = None
    message: str | None = None


# ---- Endpoints ----

@router.post("/learning-plan/{kb_name}/generate")
async def generate_learning_plan(kb_name: str):
    """Generate a personalized learning plan from the knowledge graph.

    Analyses weak points (mastery < 0.3), resolves prerequisite chains,
    and produces a day-by-day study plan with goals, exercises, and time estimates.
    """
    plan = await generate_plan(kb_name)
    if plan is None:
        raise HTTPException(
            status_code=404,
            detail=f"Knowledge graph '{kb_name}' not found. Create one first via the knowledge-graph API.",
        )

    save_plan(kb_name, plan)
    return plan


@router.get("/learning-plan/{kb_name}")
async def get_learning_plan(kb_name: str):
    """Retrieve the current cached learning plan for a knowledge base."""
    plan = get_cached_plan(kb_name)
    if plan is None:
        raise HTTPException(
            status_code=404,
            detail=f"No learning plan found for '{kb_name}'. Call POST .../generate first.",
        )
    return plan
