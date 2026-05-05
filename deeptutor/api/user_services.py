"""Per-user service factory. Returns the correct service instance based on request.state.user_id."""

from functools import lru_cache
from typing import Optional

from fastapi import Request

from deeptutor.services.path_service import get_path_service
from deeptutor.services.notebook import NotebookManager


@lru_cache(maxsize=32)
def get_notebook_manager_for_user(user_id: Optional[str]) -> NotebookManager:
    """Get notebook manager scoped to user directory."""
    base = get_path_service().get_workspace_root() / "notebook"
    if user_id:
        user_dir = base / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return NotebookManager(base_dir=str(user_dir))
    return NotebookManager(base_dir=str(base))


async def notebook_dep(request: Request) -> NotebookManager:
    """FastAPI dependency: return notebook manager for current user."""
    user_id = getattr(request.state, "user_id", None) if hasattr(request, "state") else None
    return get_notebook_manager_for_user(user_id)
