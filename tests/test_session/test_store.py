"""SessionStore 单元测试"""
import pytest
import json
import shutil
from pathlib import Path
from skywalker.session.store import SessionStore, SessionMeta
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
def sample_messages():
    """示例消息列表"""
    return [
        Message(Role.USER, "你好"),
        Message(Role.ASSISTANT, "你好！有什么可以帮你的？"),
        Message(Role.USER, "帮我写一个函数"),
        Message(Role.ASSISTANT, "好的，请问是什么语言？"),
    ]


@pytest.fixture
def sample_meta():
    """示例会话元数据"""
    return SessionMeta(
        session_id="20260101-120000",
        title="测试会话",
        created_at="2026-01-01T12:00:00",
        updated_at="2026-01-01T12:00:00",
        project_root="/test/project",
        summary="测试摘要",
        message_count=4,
    )


class TestSessionStore:
    """SessionStore 测试类"""

    def test_create_session_dir(self, store):
        """测试创建会话目录"""
        session_id = "20260101-120000"
        path = store.create_session_dir(session_id)
        assert path.exists()
        assert path.is_dir()
        assert path.name == session_id

    def test_create_session_dir_exists(self, store):
        """测试创建已存在的会话目录不报错"""
        session_id = "20260101-120000"
        store.create_session_dir(session_id)
        path = store.create_session_dir(session_id)  # 再次创建
        assert path.exists()

    def test_save_and_load_meta(self, store, sample_meta):
        """测试保存和加载 meta"""
        store.create_session_dir(sample_meta.session_id)
        store.save_meta(sample_meta.session_id, sample_meta)

        loaded = store.load_meta(sample_meta.session_id)
        assert loaded is not None
        assert loaded.session_id == sample_meta.session_id
        assert loaded.title == sample_meta.title
        assert loaded.project_root == sample_meta.project_root
        assert loaded.message_count == sample_meta.message_count

    def test_load_meta_not_exists(self, store):
        """测试加载不存在的 meta 返回 None"""
        loaded = store.load_meta("nonexistent")
        assert loaded is None

    def test_save_and_load_messages(self, store, sample_messages):
        """测试保存和加载消息"""
        session_id = "20260101-120000"
        store.create_session_dir(session_id)
        store.save_messages(session_id, sample_messages)

        loaded = store.load_messages(session_id)
        assert len(loaded) == len(sample_messages)
        assert loaded[0].role == Role.USER
        assert loaded[0].content == "你好"
        assert loaded[1].role == Role.ASSISTANT
        assert loaded[1].content == "你好！有什么可以帮你的？"

    def test_load_messages_not_exists(self, store):
        """测试加载不存在的消息返回空列表"""
        loaded = store.load_messages("nonexistent")
        assert loaded == []

    def test_save_messages_with_tool_calls(self, store):
        """测试保存包含工具调用的消息"""
        session_id = "20260101-120000"
        store.create_session_dir(session_id)

        messages = [
            Message(Role.USER, "查看文件"),
            Message(Role.ASSISTANT, [
                {"type": "text", "text": "我来帮你查看"},
                {"type": "tool_use", "id": "call_1", "name": "file_tool", "input": {"path": "/test"}},
            ]),
            Message(Role.USER, [
                {"type": "tool_result", "tool_use_id": "call_1", "content": "文件内容"},
            ]),
        ]

        store.save_messages(session_id, messages)
        loaded = store.load_messages(session_id)

        assert len(loaded) == 3
        assert isinstance(loaded[1].content, list)
        assert loaded[1].content[1]["type"] == "tool_use"

    def test_list_sessions_empty(self, store):
        """测试空目录返回空列表"""
        sessions = store.list_sessions()
        assert sessions == []

    def test_list_sessions(self, store, sample_meta):
        """测试列出所有会话"""
        # 创建两个会话
        store.create_session_dir("20260101-120000")
        store.save_meta("20260101-120000", sample_meta)

        meta2 = SessionMeta(
            session_id="20260102-120000",
            title="第二个会话",
            created_at="2026-01-02T12:00:00",
            updated_at="2026-01-02T12:00:00",
            project_root="/test/project",
        )
        store.create_session_dir("20260102-120000")
        store.save_meta("20260102-120000", meta2)

        sessions = store.list_sessions()
        assert len(sessions) == 2
        # 按时间倒序，最新的在前
        assert sessions[0].session_id == "20260102-120000"
        assert sessions[1].session_id == "20260101-120000"

    def test_delete_session(self, store, sample_meta):
        """测试删除会话"""
        session_id = sample_meta.session_id
        store.create_session_dir(session_id)
        store.save_meta(session_id, sample_meta)

        assert store.delete_session(session_id) is True
        assert not (store._base_dir / session_id).exists()

    def test_delete_session_not_exists(self, store):
        """测试删除不存在的会话返回 False"""
        assert store.delete_session("nonexistent") is False

    def test_save_session_memory(self, store):
        """测试保存会话级记忆"""
        from skywalker.memory.base import MemoryEntry, MemoryType
        from datetime import datetime, timezone

        session_id = "20260101-120000"
        store.create_session_dir(session_id)

        entries = [
            MemoryEntry(
                id="entry-1",
                type=MemoryType.FACT,
                content="用户喜欢 Python",
                importance=0.8,
                source="session",
                create_at=datetime.now(timezone.utc),
                tags=["preference"],
            )
        ]

        store.save_session_memory(session_id, entries)
        memory_path = store._base_dir / session_id / "memory.md"
        assert memory_path.exists()
        content = memory_path.read_text(encoding="utf-8")
        assert "Python" in content
