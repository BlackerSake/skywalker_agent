
from __future__ import annotations
import asyncio
import os
from pathlib import Path

from prompt_toolkit import output
from skywalker.tools.base import ToolResult, ToolError


class GitWorkTree:
    """Git Worktree 沙箱，为高风险操作提供隔离执行环境"""
    def __init__(self, 
                project_root: str, 
                sandbox_dir: str = ".skywalker-sandbox"):
        self.project_root = Path(project_root).resolve()
        self.sandbox_dir = self.project_root / sandbox_dir

    async def setup(self) -> None:
        """创建 worktree，若已存在先移除"""
        if self.sandbox_dir.exists():
            await self._run_git("worktree", "remove", "--force", str(self.sandbox_dir))
        await self._run_git("worktree", "add", str(self.sandbox_dir), "HEAD")
    async def run(self, cmd: str, timeout: int) -> ToolResult | ToolError:
        """在 worktree 目录内执行命令"""
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=str(self.sandbox_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
            output = stdout.decode() + stderr.decode()
            return ToolResult(tool_call_id="", output=output)
        except asyncio.TimeoutError:
            proc.kill()
            return ToolError(tool_call_id="", error="命令在 {timeout}s 后超时", reason="timeout")

    async def commit_changes(self) -> str:
        """提交沙箱内的变更，返回 diff 摘要"""
        result = await self._run_git("-C", str(self.sandbox_dir), "diff", "--stat")
        diff_summary = result.stdout.decode().strip()
        await self._run_git("-C", str(self.sandbox_dir), "add", "-A")
        await self._run_git("-C", str(self.sandbox_dir), "commit", "-m", "skywalker sandbox changes")
        return diff_summary
    async def cleanup(self) -> None:
        await self._run_git("worktree", "remove", "--force", str(self.sandbox_dir))

    async def _run_git(self, *args: str) -> asyncio.subprocess.Process:
        """执行 git 命令的内部辅助方法"""
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        return proc
    async def __aenter__(self) ->  GitWorkTree:
        await self.setup()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.cleanup()

    
