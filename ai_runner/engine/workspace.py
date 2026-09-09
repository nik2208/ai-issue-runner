"""Workspace and Git branch manager."""

import os
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List

class WorkspaceManager:
    def __init__(self, workspace_dir: str | Path):
        self.workspace_dir = Path(workspace_dir).resolve()

    async def run_git(self, *args: str) -> tuple[int, str, str]:
        cmd = ["git"] + list(args)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(self.workspace_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return (
            proc.returncode,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace")
        )

    async def is_git_repo(self) -> bool:
        code, _, _ = await self.run_git("rev-parse", "--is-inside-work-tree")
        return code == 0

    async def init_git_repo(self) -> bool:
        if not await self.is_git_repo():
            code, _, _ = await self.run_git("init")
            return code == 0
        return True

    async def get_current_branch(self) -> str:
        code, out, _ = await self.run_git("rev-parse", "--abbrev-ref", "HEAD")
        return out.strip() if code == 0 else "main"

    async def create_and_checkout_branch(self, branch_name: str) -> bool:
        code, _, _ = await self.run_git("checkout", "-B", branch_name)
        return code == 0

    async def get_diff(self) -> str:
        code, out, _ = await self.run_git("diff")
        if code == 0 and out:
            return out
        # Also check untracked diff if no tracked changes
        code, out, _ = await self.run_git("status", "--porcelain")
        return out

    async def commit_changes(self, message: str) -> bool:
        await self.run_git("add", "-A")
        code, _, _ = await self.run_git("commit", "-m", message)
        return code == 0
