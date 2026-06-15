"""skywalker.tools.executor 测试"""
import pytest
from unittest.mock import patch, AsyncMock

from skywalker.tools.base import ToolBase, ToolResult, ToolError
from skywalker.tools.registry import ToolRegistry
from skywalker.tools.executor import ToolExecutor
from skywalker.llm.base import ToolCall


def _make_tool(name: str, output: str = "ok") -> ToolBase:
    class _T(ToolBase):
        async def execute(self, arguments: dict) -> ToolResult | ToolError:
            return ToolResult(tool_call_id="", output=output)

    t = _T()
    t.name = name
    t.description = ""
    t.parameters = {}
    return t


@pytest.fixture
def registry():
    reg = ToolRegistry()
    reg.register(_make_tool("echo"))
    return reg


@pytest.fixture
def executor():
    return ToolExecutor(sandbox=None)


# ── run_one ─────────────────────────────────────────────────

class TestRunOne:
    @pytest.mark.asyncio
    async def test_normal_execution(self, executor, registry):
        tc = ToolCall(id="1", name="echo", arguments={})
        result = await executor.run_one(tc, registry)
        assert isinstance(result, ToolResult)
        assert result.output == "ok"

    @pytest.mark.asyncio
    async def test_tool_not_found(self, executor, registry):
        tc = ToolCall(id="1", name="nonexistent", arguments={})
        result = await executor.run_one(tc, registry)
        assert isinstance(result, ToolError)
        assert result.reason == "execution_error"

    @pytest.mark.asyncio
    async def test_deny_pattern_blocks_command(self, executor, registry):
        """命中 deny pattern 返回 ToolError(reason='denied')"""
        shell_tool = _make_tool("shell")
        registry.register(shell_tool)
        tc = ToolCall(id="1", name="shell", arguments={"command": "rm -rf /"})
        result = await executor.run_one(tc, registry)
        assert isinstance(result, ToolError)
        assert result.reason == "denied"

    @pytest.mark.asyncio
    async def test_ask_pattern_user_rejects(self, executor, registry):
        """命中 ask pattern + 用户拒绝 → reason='user_rejected'"""
        shell_tool = _make_tool("shell")
        registry.register(shell_tool)
        tc = ToolCall(id="1", name="shell", arguments={"command": "rm foo.txt"})
        with patch("builtins.input", return_value="n"):
            result = await executor.run_one(tc, registry)
        assert isinstance(result, ToolError)
        assert result.reason == "user_rejected"

    @pytest.mark.asyncio
    async def test_ask_pattern_user_accepts(self, executor, registry):
        """命中 ask pattern + 用户同意 → 正常执行"""
        shell_tool = _make_tool("shell")
        registry.register(shell_tool)
        tc = ToolCall(id="1", name="shell", arguments={"command": "rm foo.txt"})
        with patch("builtins.input", return_value="y"):
            result = await executor.run_one(tc, registry)
        assert isinstance(result, ToolResult)


# ── run_all ─────────────────────────────────────────────────

class TestRunAll:
    @pytest.mark.asyncio
    async def test_parallel_execution(self, executor, registry):
        tcs = [
            ToolCall(id="1", name="echo", arguments={}),
            ToolCall(id="2", name="echo", arguments={}),
        ]
        results = await executor.run_all(tcs, registry)
        assert len(results) == 2
        assert all(isinstance(r, ToolResult) for r in results)

    @pytest.mark.asyncio
    async def test_mixed_results(self, executor, registry):
        tcs = [
            ToolCall(id="1", name="echo", arguments={}),
            ToolCall(id="2", name="nonexistent", arguments={}),
        ]
        results = await executor.run_all(tcs, registry)
        assert len(results) == 2
        assert isinstance(results[0], ToolResult)
        assert isinstance(results[1], ToolError)


# ── _check_deny / _check_ask ────────────────────────────────

class TestPatternCheck:
    def test_deny_rm_rf(self, executor):
        assert executor._check_deny("rm -rf /") is True

    def test_deny_normal_command(self, executor):
        assert executor._check_deny("ls -la") is False

    def test_ask_rm(self, executor):
        assert executor._check_ask("rm file.txt") is True

    def test_ask_sudo(self, executor):
        assert executor._check_ask("sudo apt install x") is True

    def test_ask_normal_command(self, executor):
        assert executor._check_ask("cat file.txt") is False
