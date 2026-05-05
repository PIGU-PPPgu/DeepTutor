"""
Podcast API Router
==================

NotebookLM 式播客生成 API。

端点：
- POST /api/v1/audio/{kb_name}/podcast — 生成播客
- GET  /api/v1/audio/{kb_name}/podcast/{task_id} — 获取播客状态/音频
- GET  /api/v1/audio/{kb_name}/podcasts — 列出播客
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from deeptutor.capabilities.audio_companion import (
    AudioCompanionCapability,
    get_podcast_task,
    list_podcast_tasks,
)
from deeptutor.knowledge.manager import KnowledgeBaseManager
from deeptutor.logging import get_logger

logger = get_logger("audio_api")
router = APIRouter()


class PodcastRequest(BaseModel):
    """播客生成请求。"""
    content: Optional[str] = None  # 直接提供内容
    title: str = ""  # 播客标题
    use_knowledge: bool = True  # 是否从知识库读取内容


class PodcastResponse(BaseModel):
    """播客生成响应。"""
    task_id: str
    status: str
    title: str
    message: str


@router.post("/{kb_name}/podcast", response_model=PodcastResponse)
async def create_podcast(kb_name: str, request: PodcastRequest):
    """
    生成播客：从知识库内容或直接提供的文本生成双人对话播客。
    返回 task_id 用于轮询状态。
    """
    content = request.content or ""

    # 如果没有直接提供内容，尝试从知识库读取
    if not content and request.use_knowledge:
        try:
            kb_manager = KnowledgeBaseManager(kb_name)
            # 获取知识库摘要作为播客内容
            docs = kb_manager.list_documents()
            if docs:
                # 拼接文档内容（截断到合理长度）
                text_parts = []
                for doc in docs[:10]:  # 最多取10个文档
                    try:
                        doc_content = kb_manager.get_document_content(doc)
                        if doc_content:
                            text_parts.append(doc_content[:2000])
                    except Exception:
                        pass
                content = "\n\n".join(text_parts)
        except Exception as e:
            logger.warning("Failed to read knowledge base %s: %s", kb_name, e)

    if not content or len(content.strip()) < 20:
        raise HTTPException(
            status_code=400,
            detail="内容不足，请提供更多学习内容（至少20字符）或确保知识库中有文档。",
        )

    capability = AudioCompanionCapability()
    task = await capability.generate_podcast(
        kb_name=kb_name,
        content=content,
        title=request.title,
    )

    return PodcastResponse(
        task_id=task.task_id,
        status=task.status,
        title=task.title,
        message=f"播客生成任务已创建，请通过 GET /audio/{kb_name}/podcast/{task.task_id} 查看进度。",
    )


@router.get("/{kb_name}/podcast/{task_id}")
async def get_podcast(kb_name: str, task_id: str):
    """
    获取播客生成状态，完成后返回音频流。
    """
    task = get_podcast_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="播客任务不存在")
    if task.kb_name != kb_name:
        raise HTTPException(status_code=404, detail="播客任务不存在")

    # 未完成：返回状态信息
    if task.status != "completed":
        return {
            "task_id": task.task_id,
            "status": task.status,
            "progress": task.progress,
            "title": task.title,
            "error": task.error,
            "dialogue": task.dialogue,
        }

    # 已完成但没有音频文件：返回脚本
    if not task.output_path or not task.output_path.exists():
        return {
            "task_id": task.task_id,
            "status": "completed",
            "title": task.title,
            "has_audio": False,
            "script": task.enhanced_script,
            "dialogue": task.dialogue,
        }

    # 已完成且有音频：返回音频流
    return FileResponse(
        path=str(task.output_path),
        media_type="audio/mpeg",
        filename=f"podcast_{task.title or task_id}.mp3",
        headers={
            "Content-Disposition": f'inline; filename="podcast_{task_id}.mp3"',
        },
    )


@router.get("/{kb_name}/podcasts")
async def list_podcasts(kb_name: str):
    """列出知识库的所有播客任务。"""
    tasks = list_podcast_tasks(kb_name)
    return {
        "kb_name": kb_name,
        "podcasts": [t.to_dict() for t in tasks],
    }
