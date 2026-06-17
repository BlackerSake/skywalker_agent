"""系统命令单元测试"""
import pytest
from skywalker.commands.builtin.system import HelpCommand, ExitCommand, StatusCommand
from skywalker.commands.base import CommandBase, CommandResult
from skywalker.commands.registry import CommandRegistry
from skywalker.core import AgentState, Message, Role


@pytest.fixture
def registry():
    """创建 CommandRegistry 实例"""
    return CommandRegistry()


@pytest.fixture
def agent_state():
    """创建带消息的 AgentState"""
    state = AgentState(project_root="/test/project")
    state.messages = [
        Message(Role.USER, "你好"),
        Message(Role.ASSISTANT, "你好！"),
    ]
    return state


class TestHelpCommand:
    """HelpCommand 测试"""

    @pytest.mark.asyncio
    async def test_help_output(self, registry, agent_state):
        """测试帮助输出包含所有命令"""

        class TestCmdImpl(CommandBase):
            name = "test"
            description = "测试命令"
            usage = "/test [arg]"

            async def execute(self, args, ctx):
                return CommandResult(output="")

        registry.register(TestCmdImpl())
        cmd = HelpCommand(registry)

        result = await cmd.execute([], agent_state)

        assert "Available commands" in result.output
        assert "/test [arg]" in result.output
        assert "测试命令" in result.output

    @pytest.mark.asyncio
    async def test_help_should_continue(self, registry, agent_state):
        """测试帮助命令返回 should_continue=True"""
        cmd = HelpCommand(registry)
        result = await cmd.execute([], agent_state)
        assert result.should_complete is True


class TestExitCommand:
    """ExitCommand 测试"""

    @pytest.mark.asyncio
    async def test_exit_output(self, agent_state):
        """测试退出命令输出"""
        cmd = ExitCommand()
        result = await cmd.execute([], agent_state)

        assert "Sayounara" in result.output

    @pytest.mark.asyncio
    async def test_exit_should_complete(self, agent_state):
        """测试退出命令返回 should_complete=True"""
        cmd = ExitCommand()
        result = await cmd.execute([], agent_state)
        assert result.should_complete is True


class TestStatusCommand:
    """StatusCommand 测试"""

    @pytest.mark.asyncio
    async def test_status_output(self, agent_state):
        """测试状态命令输出"""
        # 创建模拟的 session_manager
        class MockSessionManager:
            @property
            def current_session_id(self):
                return "test-session-123"

        cmd = StatusCommand(MockSessionManager())
        result = await cmd.execute([], agent_state)

        assert "项目目录: /test/project" in result.output
        assert "消息数量: 2" in result.output
        assert "test-session-123" in result.output
        assert "Token 用量" in result.output

    @pytest.mark.asyncio
    async def test_status_no_session(self, agent_state):
        """测试无会话时的状态命令"""

        class MockSessionManager:
            @property
            def current_session_id(self):
                return None

        cmd = StatusCommand(MockSessionManager())
        result = await cmd.execute([], agent_state)

        assert "当前会话: 无" in result.output

    @pytest.mark.asyncio
    async def test_status_empty_messages(self):
        """测试空消息的状态命令"""
        state = AgentState(project_root="/test")

        class MockSessionManager:
            @property
            def current_session_id(self):
                return "test"

        cmd = StatusCommand(MockSessionManager())
        result = await cmd.execute([], state)

        assert "消息数量: 0" in result.output
