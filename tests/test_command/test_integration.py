"""命令系统集成测试"""
import pytest
import asyncio
from pathlib import Path
from skywalker.commands.registry import CommandRegistry
from skywalker.commands.builtin import register_builtin_commands
from skywalker.session.store import SessionStore
from skywalker.session.manager import SessionManager
from skywalker.core import AgentState, Message, Role


@pytest.fixture
def tmp_sessions(tmp_path):
    """创建临时会话目录"""
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    return sessions_dir


@pytest.fixture
def store(tmp_sessions):
    """创建 SessionStore 实例"""
    return SessionStore(base_dir=str(tmp_sessions))


@pytest.fixture
def manager(store):
    """创建 SessionManager 实例"""
    return SessionManager(store)


@pytest.fixture
def registry(manager):
    """创建 CommandRegistry 实例并注册所有命令"""
    reg = CommandRegistry()
    register_builtin_commands(reg, session_manager=manager)
    return reg


@pytest.fixture
def agent_state():
    """创建 AgentState"""
    return AgentState(project_root="/test")


class TestCommandIntegration:
    """命令系统集成测试"""

    @pytest.mark.asyncio
    async def test_help_command(self, registry, agent_state):
        """测试 /help 命令"""
        result = await registry.dispatch("/help", agent_state)

        assert "Available commands" in result.output
        assert "/help" in result.output
        assert "/exit" in result.output
        assert "/save" in result.output
        assert "/list" in result.output

    @pytest.mark.asyncio
    async def test_save_and_list(self, registry, manager, agent_state):
        """测试 /save 和 /list 命令"""
        # 创建会话并添加消息
        manager.new_session("/test")
        manager.add_message(Message(Role.USER, "你好"))
        manager.add_message(Message(Role.ASSISTANT, "你好！"))

        # 保存会话
        save_result = await registry.dispatch("/save 测试会话", agent_state)
        assert "保存成功" in save_result.output

        # 列出会话
        list_result = await registry.dispatch("/list", agent_state)
        assert "历史会话" in list_result.output
        assert "测试会话" in list_result.output

    @pytest.mark.asyncio
    async def test_rename_and_list(self, registry, manager, agent_state):
        """测试 /rename 和 /list 命令"""
        # 创建会话
        session_id = manager.new_session("/test")
        manager.add_message(Message(Role.USER, "测试"))
        await manager.save_session()

        # 重命名
        rename_result = await registry.dispatch("/rename 新名称", agent_state)
        assert "已重命名为" in rename_result.output

        # 列出验证
        list_result = await registry.dispatch("/list", agent_state)
        assert "新名称" in list_result.output

    @pytest.mark.asyncio
    async def test_resume_command(self, registry, manager, agent_state):
        """测试 /resume 命令"""
        # 创建并保存会话
        session_id = manager.new_session("/test")
        manager.add_message(Message(Role.USER, "你好"))
        manager.add_message(Message(Role.ASSISTANT, "你好！"))
        await manager.save_session(title="恢复测试")

        # 恢复会话
        resume_result = await registry.dispatch(f"/resume {session_id}", agent_state)
        assert "恢复会话" in resume_result.output

    @pytest.mark.asyncio
    async def test_delete_command(self, registry, manager, agent_state):
        """测试 /delete 命令"""
        # 创建并保存会话
        session_id = manager.new_session("/test")
        manager.add_message(Message(Role.USER, "测试"))
        await manager.save_session()

        # 删除会话
        delete_result = await registry.dispatch(f"/delete {session_id}", agent_state)
        assert "已删除会话" in delete_result.output

        # 验证已删除
        list_result = await registry.dispatch("/list", agent_state)
        assert "没有历史会话" in list_result.output

    @pytest.mark.asyncio
    async def test_unknown_command(self, registry, agent_state):
        """测试未知命令"""
        result = await registry.dispatch("/unknown", agent_state)
        assert "Unknown command" in result.output

    @pytest.mark.asyncio
    async def test_full_workflow(self, registry, manager, agent_state):
        """测试完整工作流程"""
        # 1. 创建新会话
        manager.new_session("/test")

        # 2. 添加消息
        manager.add_message(Message(Role.USER, "帮我写一个 Python 函数"))
        manager.add_message(Message(Role.ASSISTANT, "好的，请问是什么功能？"))
        manager.add_message(Message(Role.USER, "计算斐波那契数列"))
        manager.add_message(Message(Role.ASSISTANT, "这是递归实现..."))

        # 3. 保存会话
        save_result = await registry.dispatch("/save Python学习", agent_state)
        assert "保存成功" in save_result.output

        # 4. 列出会话
        list_result = await registry.dispatch("/list", agent_state)
        assert "Python学习" in list_result.output
        assert "4 条消息" in list_result.output

        # 5. 重命名
        rename_result = await registry.dispatch("/rename Python斐波那契", agent_state)
        assert "已重命名为" in rename_result.output

        # 6. 再次列出验证
        list_result = await registry.dispatch("/list", agent_state)
        assert "Python斐波那契" in list_result.output

        # 7. 获取状态
        status_result = await registry.dispatch("/status", agent_state)
        assert "项目目录" in status_result.output
