"""CommandRegistry 单元测试"""
import pytest
import asyncio
from skywalker.commands.base import CommandBase, CommandResult
from skywalker.commands.registry import CommandRegistry
from skywalker.core import AgentState


class MockCommand(CommandBase):
    """模拟命令，用于测试"""
    name = "mock"
    description = "模拟命令"
    usage = "/mock [arg]"

    def __init__(self):
        self.last_args = None
        self.last_ctx = None

    async def execute(self, args: list[str], ctx: AgentState) -> CommandResult:
        self.last_args = args
        self.last_ctx = ctx
        return CommandResult(output=f"mock executed with {args}")


class ExitMockCommand(CommandBase):
    """模拟退出命令"""
    name = "exit"
    description = "退出"
    usage = "/exit"

    async def execute(self, args: list[str], ctx: AgentState) -> CommandResult:
        return CommandResult(output="再见", should_complete=False)


@pytest.fixture
def registry():
    """创建 CommandRegistry 实例"""
    return CommandRegistry()


@pytest.fixture
def mock_command():
    """创建 MockCommand 实例"""
    return MockCommand()


@pytest.fixture
def agent_state():
    """创建 AgentState 实例"""
    return AgentState(project_root="/test")


class TestCommandRegistry:
    """CommandRegistry 测试类"""

    def test_register(self, registry, mock_command):
        """测试注册命令"""
        registry.register(mock_command)
        assert registry.get("mock") is mock_command

    def test_register_overwrite(self, registry, mock_command):
        """测试重复注册覆盖"""
        registry.register(mock_command)
        new_mock = MockCommand()
        registry.register(new_mock)
        assert registry.get("mock") is new_mock

    def test_get_not_exists(self, registry):
        """测试获取不存在的命令返回 None"""
        assert registry.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_dispatch(self, registry, mock_command, agent_state):
        """测试分发命令"""
        registry.register(mock_command)

        result = await registry.dispatch("/mock arg1 arg2", agent_state)

        assert result.output == "mock executed with ['arg1', 'arg2']"
        assert mock_command.last_args == ["arg1", "arg2"]
        assert mock_command.last_ctx is agent_state

    @pytest.mark.asyncio
    async def test_dispatch_no_args(self, registry, mock_command, agent_state):
        """测试分发无参数命令"""
        registry.register(mock_command)

        result = await registry.dispatch("/mock", agent_state)

        assert result.output == "mock executed with []"
        assert mock_command.last_args == []

    @pytest.mark.asyncio
    async def test_dispatch_unknown_command(self, registry, agent_state):
        """测试分发未知命令"""
        result = await registry.dispatch("/unknown", agent_state)

        assert "Unknown command" in result.output
        assert "unknown" in result.output

    @pytest.mark.asyncio
    async def test_dispatch_should_complete(self, registry, agent_state):
        """测试命令返回 should_complete=False"""
        exit_cmd = ExitMockCommand()
        registry.register(exit_cmd)

        result = await registry.dispatch("/exit", agent_state)

        assert result.output == "再见"
        assert result.should_complete is False

    def test_help_text(self, registry, mock_command):
        """测试生成帮助文本"""
        registry.register(mock_command)

        help_text = registry.help_text()

        assert "Available commands" in help_text
        assert "/mock [arg]" in help_text
        assert "模拟命令" in help_text

    def test_help_text_multiple_commands(self, registry):
        """测试多个命令的帮助文本"""
        class Cmd1(CommandBase):
            name = "cmd1"
            description = "命令1"
            usage = "/cmd1"

            async def execute(self, args, ctx):
                return CommandResult(output="")

        class Cmd2(CommandBase):
            name = "cmd2"
            description = "命令2"
            usage = "/cmd2 [arg]"

            async def execute(self, args, ctx):
                return CommandResult(output="")

        registry.register(Cmd1())
        registry.register(Cmd2())

        help_text = registry.help_text()

        assert "/cmd1" in help_text
        assert "/cmd2 [arg]" in help_text
        assert "命令1" in help_text
        assert "命令2" in help_text
