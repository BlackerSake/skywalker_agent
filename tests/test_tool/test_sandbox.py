"""skywalker.tools.sandbox 测试"""
import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

from skywalker.tools.base import ToolResult, ToolError
from skywalker.tools.sandbox import GitWorkTree


@pytest.fixture
def sandbox(tmp_path):
    """在临时目录创建 sandbox 实例"""
    return GitWorkTree(project_root=str(tmp_path), sandbox_dir=".test-sandbox")


class TestGitWorkTreeInit:
    def test_paths(self, sandbox, tmp_path):
        assert sandbox.project_root == tmp_path.resolve()
        assert sandbox.sandbox_dir == (tmp_path / ".test-sandbox").resolve()


class TestGitWorkTreeRun:
    @pytest.mark.asyncio
    async def test_run_echo(self, sandbox, tmp_path):
        """在 worktree 目录内执行命令"""
        sandbox.sandbox_dir.mkdir(parents=True, exist_ok=True)
        result = await sandbox.run("echo hello", timeout=5)
        assert isinstance(result, ToolResult)
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_run_timeout(self, sandbox, tmp_path):
        sandbox.sandbox_dir.mkdir(parents=True, exist_ok=True)
        result = await sandbox.run("sleep 100", timeout=1)
        assert isinstance(result, ToolError)
        assert result.reason == "timeout"


class TestGitWorkTreeContextManager:
    @pytest.mark.asyncio
    async def test_context_manager_calls_setup_and_cleanup(self, sandbox):
        """async with 调用 setup 和 cleanup"""
        with patch.object(sandbox, "setup", new_callable=AsyncMock) as mock_setup, \
             patch.object(sandbox, "cleanup", new_callable=AsyncMock) as mock_cleanup:
            async with sandbox:
                pass
            mock_setup.assert_called_once()
            mock_cleanup.assert_called_once()
