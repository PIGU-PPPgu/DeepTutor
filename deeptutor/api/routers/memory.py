"""Two-file public memory API: SUMMARY and PROFILE (user-isolated)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deeptutor.api.auth_deps import get_optional_user
from deeptutor.services.memory import MemoryFile, MemoryService
from deeptutor.services.session import get_sqlite_session_store

router = APIRouter()

_VALID_FILES: set[MemoryFile] = {"summary", "profile"}


def _snap_dict(snap) -> dict:
    return {
        "summary": snap.summary,
        "profile": snap.profile,
        "summary_updated_at": snap.summary_updated_at,
        "profile_updated_at": snap.profile_updated_at,
    }


class FileUpdateRequest(BaseModel):
    file: MemoryFile
    content: str = ""


class MemoryRefreshRequest(BaseModel):
    session_id: str | None = None
    language: str = "en"


class MemoryClearRequest(BaseModel):
    file: MemoryFile | None = None


def _get_user_memory_service(user: dict | None) -> MemoryService:
    """Get memory service scoped to the current user."""
    user_id = str(user.get("uid", user.get("username"))) if user else None
    return MemoryService(user_id=user_id)


@router.get("")
async def get_memory(user: dict | None = Depends(get_optional_user)):
    return _snap_dict(_get_user_memory_service(user).read_snapshot())


@router.put("")
async def update_memory(
    payload: FileUpdateRequest,
    user: dict | None = Depends(get_optional_user),
):
    if payload.file not in _VALID_FILES:
        raise HTTPException(status_code=400, detail=f"Invalid file: {payload.file}")
    snap = _get_user_memory_service(user).write_file(payload.file, payload.content)
    return {**_snap_dict(snap), "saved": True}


@router.post("/refresh")
async def refresh_memory(
    payload: MemoryRefreshRequest,
    user: dict | None = Depends(get_optional_user),
):
    store = get_sqlite_session_store()
    session_id = str(payload.session_id or "").strip()
    if session_id:
        user_id = str(user.get("uid", user.get("username"))) if user else None
        session = await store.get_session(session_id, user_id=user_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

    svc = _get_user_memory_service(user)
    result = await svc.refresh_from_session(
        session_id or None,
        language=payload.language,
    )
    snap = svc.read_snapshot()
    return {**_snap_dict(snap), "changed": result.changed}


@router.post("/clear")
async def clear_memory(
    payload: MemoryClearRequest | None = None,
    user: dict | None = Depends(get_optional_user),
):
    svc = _get_user_memory_service(user)
    target = payload.file if payload else None
    if target and target not in _VALID_FILES:
        raise HTTPException(status_code=400, detail=f"Invalid file: {target}")

    if target:
        snap = svc.clear_file(target)
    else:
        snap = svc.clear_memory()
    return {**_snap_dict(snap), "cleared": True}
