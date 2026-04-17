"""Git sync router — one-click upstream sync."""

from __future__ import annotations

import asyncio
import os
import subprocess
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/system", tags=["system"])

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))


class GitSyncResult(BaseModel):
    success: bool
    message: str
    current_commit: str = ""
    upstream_commit: str = ""


@router.post("/git-sync", response_model=GitSyncResult)
async def git_sync_upstream():
    """One-click sync with upstream DeepTutor repository."""
    loop = asyncio.get_event_loop()

    def _run(cmd: str) -> str:
        return subprocess.run(
            cmd, shell=True, cwd=REPO_ROOT,
            capture_output=True, text=True, timeout=120
        ).stdout.strip()

    try:
        # Ensure upstream remote exists
        remotes = await loop.run_in_executor(None, lambda: _run("git remote"))
        if "upstream" not in remotes.split("\n"):
            await loop.run_in_executor(
                None,
                lambda: _run("git remote add upstream https://github.com/HKUDS/DeepTutor.git")
            )

        # Fetch upstream
        await loop.run_in_executor(None, lambda: _run("git fetch upstream"))

        # Get current and upstream commits
        current = await loop.run_in_executor(None, lambda: _run("git rev-parse --short HEAD"))
        upstream = await loop.run_in_executor(
            None, lambda: _run("git rev-parse --short upstream/main 2>/dev/null || echo unknown")
        )

        # Check if there are local changes
        status = await loop.run_in_executor(None, lambda: _run("git status --porcelain"))
        if status:
            # Stash local changes
            await loop.run_in_executor(None, lambda: _run("git stash"))

        # Merge upstream/main
        merge_result = await loop.run_in_executor(
            None, lambda: subprocess.run(
                "git merge upstream/main --no-edit",
                shell=True, cwd=REPO_ROOT,
                capture_output=True, text=True, timeout=120
            )
        )

        if status:
            # Pop stash
            await loop.run_in_executor(None, lambda: _run("git stash pop"))

        if merge_result.returncode == 0:
            return GitSyncResult(
                success=True,
                message=f"已同步到最新版本 ({upstream})",
                current_commit=upstream,
                upstream_commit=upstream,
            )
        else:
            return GitSyncResult(
                success=False,
                message=f"合并冲突，请手动解决: {merge_result.stderr[:200]}",
                current_commit=current,
                upstream_commit=upstream,
            )
    except Exception as e:
        return GitSyncResult(success=False, message=f"同步失败: {str(e)}")


@router.get("/git-status", response_model=GitSyncResult)
async def git_status_check():
    """Check current git status vs upstream."""
    loop = asyncio.get_event_loop()

    def _run(cmd: str) -> str:
        return subprocess.run(
            cmd, shell=True, cwd=REPO_ROOT,
            capture_output=True, text=True, timeout=30
        ).stdout.strip()

    try:
        current = await loop.run_in_executor(None, lambda: _run("git rev-parse --short HEAD"))
        
        remotes = await loop.run_in_executor(None, lambda: _run("git remote"))
        if "upstream" in remotes.split("\n"):
            await loop.run_in_executor(None, lambda: _run("git fetch upstream"))
            upstream = await loop.run_in_executor(
                None, lambda: _run("git rev-parse --short upstream/main 2>/dev/null || echo unknown")
            )
        else:
            upstream = "未配置"

        behind = await loop.run_in_executor(
            None, lambda: _run("git rev-list --count HEAD..upstream/main 2>/dev/null || echo 0")
        )

        return GitSyncResult(
            success=True,
            message=f"当前版本 {current}，落后 {behind} 个提交" if behind != "0" else f"已是最新版本 ({current})",
            current_commit=current,
            upstream_commit=upstream,
        )
    except Exception as e:
        return GitSyncResult(success=False, message=f"状态检查失败: {str(e)}")
