"""Parent Report API Router — weekly reports and progress tracking for parents."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from deeptutor.capabilities.parent_report import (
    generate_progress_report,
    generate_suggestions,
    generate_weekly_report,
)
from deeptutor.services.knowledge_graph.graph_store import load_graph

router = APIRouter()


class WeeklyReportResponse(BaseModel):
    kb_name: str
    report_markdown: str


class ProgressReportResponse(BaseModel):
    kb_name: str
    report_markdown: str


class SuggestionsResponse(BaseModel):
    kb_name: str
    suggestions: dict


@router.get("/parent-report/{kb_name}/weekly")
async def get_weekly_report(kb_name: str):
    """生成家长周报（Markdown 格式）。

    基于知识图谱的掌握度数据，生成一份温暖专业的学习周报。
    """
    graph = load_graph(kb_name)
    if not graph:
        raise HTTPException(status_code=404, detail=f"知识图谱「{kb_name}」不存在")

    report = await generate_weekly_report(kb_name)
    return WeeklyReportResponse(kb_name=kb_name, report_markdown=report)


@router.get("/parent-report/{kb_name}/progress")
async def get_progress_report(kb_name: str):
    """生成掌握度报告（Markdown 格式）。

    展示各章节掌握度、薄弱知识点和学习路径建议。
    """
    graph = load_graph(kb_name)
    if not graph:
        raise HTTPException(status_code=404, detail=f"知识图谱「{kb_name}」不存在")

    report = await generate_progress_report(kb_name)
    return ProgressReportResponse(kb_name=kb_name, report_markdown=report)


@router.get("/parent-report/{kb_name}/suggestions")
async def get_suggestions(kb_name: str):
    """获取家长辅导建议（JSON 格式）。

    包含辅导建议、讨论话题、练习方向和下周重点。
    """
    graph = load_graph(kb_name)
    if not graph:
        raise HTTPException(status_code=404, detail=f"知识图谱「{kb_name}」不存在")

    suggestions = await generate_suggestions(kb_name)
    return SuggestionsResponse(kb_name=kb_name, suggestions=suggestions)
