"""CommandBase 和 CommandResult 单元测试"""
import pytest
from skywalker.commands.base import CommandBase, CommandResult
from skywalker.core import AgentState


class TestCommandResult:
    """CommandResult 测试"""

    def test_default_values(self):
        """测试默认值"""
        result = CommandResult(output="测试输出")
        assert result.output == "测试输出"
        assert result.should_complete is True

    def test_should_complete_false(self):
        """测试 should_complete=False"""
        result = CommandResult(output="退出", should_complete=False)
        assert result.should_complete is False

    def test_empty_output(self):
        """测试空输出"""
        result = CommandResult(output="")
        assert result.output == ""


class ConcreteCommand(CommandBase):
    """具体命令实现，用于测试"""
    name = "test"
    description = "测试命令"
    usage = "/test [args]"

    async def execute(self, args: list[str], ctx: AgentState) -> CommandResult:
        return CommandResult(output=f"执行: {args}")


class TestCommandBase:
    """CommandBase 测试"""

    def test_command_attributes(self):
        """测试命令属性"""
        cmd = ConcreteCommand()
        assert cmd.name == "test"
        assert cmd.description == "测试命令"
        assert cmd.usage == "/test [args]"

    @pytest.mark.asyncio
    async def test_command_execute(self):
        """测试命令执行"""
        cmd = ConcreteCommand()
        ctx = AgentState(project_root="/test")

        result = await cmd.execute(["arg1", "arg2"], ctx)

        assert result.output == "执行: ['arg1', 'arg2']"
        assert result.should_complete is True

    @pytest.mark.asyncio
    async def test_command_execute_no_args(self):
        """测试无参数命令执行"""
        cmd = ConcreteCommand()
        ctx = AgentState(project_root="/test")

        result = await cmd.execute([], ctx)

        assert result.output == "执行: []"
