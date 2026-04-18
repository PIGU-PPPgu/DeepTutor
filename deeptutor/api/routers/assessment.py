"""
Assessment API Router
=====================

POST /api/v1/assessment/{kb_name}/generate — 生成一套测试题
POST /api/v1/assessment/{kb_name}/submit — 提交答案并评分
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from deeptutor.capabilities.assessment import AssessmentCapability
from deeptutor.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/assessment", tags=["assessment"])

# 全局 capability 实例
_capability = AssessmentCapability()


# ── Request Models ──

class GenerateRequest(BaseModel):
    num_questions: int = Field(default=8, ge=1, le=30, description="题目数量")
    difficulty: str | None = Field(default=None, description="难度: easy/medium/hard")
    topic_filter: list[str] | None = Field(default=None, description="知识点过滤")
    subject: str = Field(default="数学", description="学科")
    content: str | None = Field(default=None, description="备用内容（无知识图谱时使用）")


class SubmitRequest(BaseModel):
    answers: dict[str, str] = Field(..., description="学生答案 {question_id: answer}")
    quiz_data: dict | None = Field(default=None, description="原始题目数据")


# ── Endpoints ──

@router.post("/{kb_name}/generate")
async def generate_assessment(kb_name: str, req: GenerateRequest):
    """生成一套自适应测试题。"""
    try:
        quiz = await _capability.generate_quiz(
            kb_name=kb_name,
            num_questions=req.num_questions,
            difficulty=req.difficulty,
            topic_filter=req.topic_filter,
            content=req.content,
            subject=req.subject,
        )
        return quiz
    except Exception as e:
        logger.error("Assessment generation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{kb_name}/submit")
async def submit_assessment(kb_name: str, req: SubmitRequest):
    """提交答案并评分。"""
    try:
        result = await _capability.submit_answers(
            kb_name=kb_name,
            answers=req.answers,
            quiz_data=req.quiz_data,
        )
        return result
    except Exception as e:
        logger.error("Assessment submission failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
