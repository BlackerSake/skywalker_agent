"""SessionManager 单元测试"""
import pytest
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from skywalker.session.store import SessionStore, SessionMeta
from skywalker.session.manager import SessionManager
from skywalker.core import Message, Role


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
def sample_messages():
    """示例消息列表"""
    return [
        Message(Role.USER, "你好"),
        Message(Role.ASSISTANT, "你好！有什么可以帮你的？"),
        Message(Role.USER, "帮我写一个函数"),
        Message(Role.ASSISTANT, "好的，请问是什么语言？"),
    ]


class TestSessionManager:
    """SessionManager 测试类"""

    def test_new_session(self, manager):
        """测试创建新会话"""
        project_root = "/test/project"
        session_id = manager.new_session(project_root)

        assert session_id is not None
        assert manager.current_session_id == session_id
        assert manager.messages == []

    def test_new_session_creates_meta(self, manager, store):
        """测试创建新会话会写入 meta"""
        session_id = manager.new_session("/test/project")

        meta = store.load_meta(session_id)
        assert meta is not None
        assert meta.session_id == session_id
        assert meta.title == "新会话"
        assert meta.project_root == "/test/project"

    def test_add_message(self, manager):
        """测试添加消息"""
        manager.new_session("/test/project")

        msg = Message(Role.USER, "你好")
        manager.add_message(msg)

        assert len(manager.messages) == 1
        assert manager.messages[0].content == "你好"

    def test_add_multiple_messages(self, manager):
        """测试添加多条消息"""
        manager.new_session("/test/project")

        manager.add_message(Message(Role.USER, "第一条"))
        manager.add_message(Message(Role.ASSISTANT, "回复第一条"))
        manager.add_message(Message(Role.USER, "第二条"))

        assert len(manager.messages) == 3

    @pytest.mark.asyncio
    async def test_save_session(self, manager, store):
        """测试保存会话"""
        session_id = manager.new_session("/test/project")
        manager.add_message(Message(Role.USER, "你好"))
        manager.add_message(Message(Role.ASSISTANT, "你好！"))

        meta = await manager.save_session()

        assert meta.session_id == session_id
        assert meta.message_count == 2

        # 验证 messages.json 已写入
        messages = store.load_messages(session_id)
        assert len(messages) == 2

    @pytest.mark.asyncio
    async def test_save_session_with_title(self, manager, store):
        """测试保存会话时指定标题"""
        session_id = manager.new_session("/test/project")
        manager.add_message(Message(Role.USER, "测试"))

        meta = await manager.save_session(title="自定义标题")

        assert meta.title == "自定义标题"

        # 验证标题已持久化
        loaded_meta = store.load_meta(session_id)
        assert loaded_meta.title == "自定义标题"

    @pytest.mark.asyncio
    async def test_save_empty_session(self, manager, store):
        """测试保存空会话（无消息）"""
        session_id = manager.new_session("/test/project")

        # 空会话应该删除会话目录
        result = await manager.save_session()
        # 当前实现：空会话删除会话目录并返回 delete_session 的结果
        assert result is True
        # 验证会话目录已被删除
        assert not (store._base_dir / session_id).exists()

    @pytest.mark.asyncio
    async def test_resume_session(self, manager, store):
        """测试恢复会话"""
        # 先创建并保存一个会话
        session_id = manager.new_session("/test/project")
        manager.add_message(Message(Role.USER, "你好"))
        manager.add_message(Message(Role.ASSISTANT, "你好！"))
        await manager.save_session()

        # 创建新 manager 恢复会话
        new_manager = SessionManager(store)
        messages = new_manager.resume_session(session_id)

        assert new_manager.current_session_id == session_id
        assert len(messages) == 2
        assert messages[0].content == "你好"
        assert messages[1].content == "你好！"

    def test_resume_session_not_exists(self, manager, store):
        """测试恢复不存在的会话"""
        messages = manager.resume_session("nonexistent")

        assert manager.current_session_id == "nonexistent"
        assert messages == []

    @pytest.mark.asyncio
    async def test_list_sessions(self, manager):
        """测试列出会话"""
        # 创建两个会话，每个都有消息
        id1 = manager.new_session("/test/project")
        manager.add_message(Message(Role.USER, "消息1"))
        await manager.save_session(title="会话1")

        id2 = manager.new_session("/test/project")
        manager.add_message(Message(Role.USER, "消息2"))
        await manager.save_session(title="会话2")

        sessions = manager.list_sessions()
        assert len(sessions) == 2
        session_ids = [s.session_id for s in sessions]
        assert id1 in session_ids
        assert id2 in session_ids

    @pytest.mark.asyncio
    async def test_delete_session(self, manager, store):
        """测试删除会话"""
        session_id = manager.new_session("/test/project")
        manager.add_message(Message(Role.USER, "测试"))
        await manager.save_session()

        result = manager.delete_session(session_id)
        assert result is True
        assert manager.current_session_id is None
        assert manager.messages == []

    @pytest.mark.asyncio
    async def test_delete_session_not_current(self, manager, store):
        """测试删除非当前会话"""
        # 创建第一个会话
        session_id1 = manager.new_session("/test/project")
        manager.add_message(Message(Role.USER, "消息1"))
        await manager.save_session(title="会话1")

        # 创建第二个会话
        session_id2 = manager.new_session("/test/project")
        manager.add_message(Message(Role.USER, "消息2"))
        await manager.save_session(title="会话2")

        # 删除第一个会话，不影响当前会话
        result = manager.delete_session(session_id1)
        assert result is True
        assert manager.current_session_id == session_id2

    def test_delete_session_not_exists(self, manager):
        """测试删除不存在的会话"""
        result = manager.delete_session("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_save_alias(self, manager, store):
        """测试 save 是 save_session 的别名"""
        session_id = manager.new_session("/test/project")
        manager.add_message(Message(Role.USER, "测试"))

        meta = await manager.save()
        assert meta.session_id == session_id

    @pytest.mark.asyncio
    async def test_resume_alias(self, manager, store):
        """测试 resume 是 resume_session 的别名"""
        session_id = manager.new_session("/test/project")
        manager.add_message(Message(Role.USER, "测试"))
        await manager.save_session()

        new_manager = SessionManager(store)
        messages = new_manager.resume(session_id)
        assert len(messages) == 1
