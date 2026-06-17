"""会话命令单元测试"""
import pytest
import pytest_asyncio
from pathlib import Path
from skywalker.commands.builtin.session import (
    SaveCommand,
    ListCommand,
    RenameCommand,
    ResumeCommand,
    DeleteCommand,
)
from skywalker.commands.base import CommandResult
from skywalker.session.store import SessionStore, SessionMeta
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
def agent_state():
    """创建 AgentState"""
    return AgentState(project_root="/test")


@pytest_asyncio.fixture
async def setup_sessions(manager):
    """创建测试会话"""
    # 创建第一个会话
    id1 = manager.new_session("/test")
    manager.add_message(Message(Role.USER, "你好"))
    manager.add_message(Message(Role.ASSISTANT, "你好！"))
    await manager.save_session(title="会话一")

    # 创建第二个会话
    id2 = manager.new_session("/test")
    manager.add_message(Message(Role.USER, "测试"))
    await manager.save_session(title="会话二")

    return id1, id2


class TestSaveCommand:
    """SaveCommand 测试"""

    @pytest.mark.asyncio
    async def test_save(self, manager):
        """测试保存命令"""
        manager.new_session("/test")
        manager.add_message(Message(Role.USER, "测试"))

        cmd = SaveCommand(manager)
        result = await cmd.execute([], AgentState())

        assert "保存成功" in result.output

    @pytest.mark.asyncio
    async def test_save_with_title(self, manager):
        """测试带标题的保存命令"""
        manager.new_session("/test")
        manager.add_message(Message(Role.USER, "测试"))

        cmd = SaveCommand(manager)
        result = await cmd.execute(["自定义标题"], AgentState())

        assert "保存成功" in result.output


class TestListCommand:
    """ListCommand 测试"""

    @pytest.mark.asyncio
    async def test_list_empty(self, manager):
        """测试列出空会话列表"""
        cmd = ListCommand(manager)
        result = await cmd.execute([], AgentState())

        assert "没有历史会话" in result.output

    @pytest.mark.asyncio
    async def test_list_with_sessions(self, manager, setup_sessions):
        """测试列出有会话的列表"""
        id1, id2 = setup_sessions
        cmd = ListCommand(manager)
        result = await cmd.execute([], AgentState())

        assert "历史会话" in result.output
        assert "会话一" in result.output
        assert "会话二" in result.output


class TestRenameCommand:
    """RenameCommand 测试"""

    @pytest.mark.asyncio
    async def test_rename(self, manager, store):
        """测试重命名命令"""
        session_id = manager.new_session("/test")
        manager.add_message(Message(Role.USER, "测试"))
        await manager.save_session()

        cmd = RenameCommand(manager)
        result = await cmd.execute(["新名称"], AgentState())

        assert "已重命名为" in result.output
        assert "新名称" in result.output

        # 验证标题已更新
        meta = store.load_meta(session_id)
        assert meta.title == "新名称"

    @pytest.mark.asyncio
    async def test_rename_no_args(self, manager):
        """测试无参数的重命名命令"""
        manager.new_session("/test")

        cmd = RenameCommand(manager)
        result = await cmd.execute([], AgentState())

        assert "用法" in result.output

    @pytest.mark.asyncio
    async def test_rename_no_session(self, manager):
        """测试无会话时的重命名命令"""
        cmd = RenameCommand(manager)
        result = await cmd.execute(["新名称"], AgentState())

        assert "当前没有会话" in result.output


class TestResumeCommand:
    """ResumeCommand 测试"""

    @pytest.mark.asyncio
    async def test_resume_with_id(self, manager, setup_sessions):
        """测试指定 session_id 的恢复命令"""
        id1, id2 = setup_sessions

        cmd = ResumeCommand(manager)
        result = await cmd.execute([id1], AgentState())

        assert "恢复会话" in result.output
        assert id1 in result.output

    @pytest.mark.asyncio
    async def test_resume_not_found(self, manager):
        """测试恢复不存在的会话"""
        cmd = ResumeCommand(manager)
        result = await cmd.execute(["nonexistent"], AgentState())

        # 当前实现：不存在的会话返回空消息列表
        assert "nonexistent" in result.output


class TestDeleteCommand:
    """DeleteCommand 测试"""

    @pytest.mark.asyncio
    async def test_delete(self, manager, setup_sessions):
        """测试删除命令"""
        id1, id2 = setup_sessions

        cmd = DeleteCommand(manager)
        result = await cmd.execute([id1], AgentState())

        assert "已删除会话" in result.output

        # 验证会话已删除
        sessions = manager.list_sessions()
        session_ids = [s.session_id for s in sessions]
        assert id1 not in session_ids

    @pytest.mark.asyncio
    async def test_delete_not_found(self, manager):
        """测试删除不存在的会话"""
        cmd = DeleteCommand(manager)
        result = await cmd.execute(["nonexistent"], AgentState())

        assert "会话不存在" in result.output
