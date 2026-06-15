"""skywalker.tools.shell_tool 测试"""
import pytest
from unittest.mock import patch

from skywalker.tools.base import ToolResult, ToolError
from skywalker.tools.shell_tool import ShellTool


@pytest.fixture
def tool():
    return ShellTool()


class TestShellTool:
    @pytest.mark.asyncio
    async def test_echo_command(self, tool):
        result = await tool.execute({"command": "echo hello"})
        assert isinstance(result, ToolResult)
        assert "exit_code: 0" in result.output
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_stderr_output(self, tool):
        result = await tool.execute({"command": "echo err >&2"})
        assert isinstance(result, ToolResult)
        assert "err" in result.output

    @pytest.mark.asyncio
    async def test_nonzero_exit_code(self, tool):
        result = await tool.execute({"command": "exit 1"})
        assert isinstance(result, ToolResult)
        assert "exit_code: 1" in result.output

    @pytest.mark.asyncio
    async def test_timeout(self, tool):
        """超时返回 ToolError(reason='timeout')"""
        with patch("skywalker.tools.shell_tool.settings") as mock_settings:
            mock_settings.tool_timeout = 1
            mock_settings.shell_max_output_tokens = 5000
            result = await tool.execute({"command": "sleep 10"})
            assert isinstance(result, ToolError)
            assert result.reason == "timeout"

    def test_schema(self, tool):
        s = tool.schema()
        assert s["name"] == "shell"
        assert "command" in s["input_schema"]["properties"]
