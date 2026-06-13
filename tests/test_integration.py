
"""
测试整个项目的链路：

6.1 启动链路
  cli/main.py → 读取 settings → long_term.load() → 注入 system prompt → 初始化 ConversationManager → 启动 loop

6.2 对话中链路
  loop: OBSERVING → ConversationManager.add_message() → 增量计算 token → should_compress() ? → 压缩

6.3 退出链路
  loop: TERMINATED → memory_manager.on_shutdown() → 提取关键信息 → 写回 MEMORY.md / USER.md
"""

import asyncio
import os
import tempfile

import pytest

from skywalker.core import AgentState, Message, Role, LoopPhase
from skywalker.memory.base import MemoryEntry, MemoryType
from skywalker.memory.long_term import LongTermMemory, MemoryManager
from skywalker.memory.short_term import ConversationManager, LLMCompressor, CompressorBase
from skywalker.memory.schema import serialize_memory_md


# ============ 测试辅助 ============

class FakeCompressor(CompressorBase):
    """模拟压缩器，不依赖 LLM"""
    async def compress(self, messages: list[Message]) -> str:
        return "这是压缩后的摘要"


class FakeLLM:
    """模拟 LLM 客户端"""
    def chat(self, messages, system=None):
        return "这是模拟回复"


def _make_entry(**kwargs) -> MemoryEntry:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    # 如果没有传入 id，则生成一个基于内容的 id
    if "id" not in kwargs:
        import hashlib
        content = kwargs.get("content", "test content")
        kwargs["id"] = hashlib.sha256(content.encode()).hexdigest()[:16]

    defaults = {
        "type": MemoryType.FACT,
        "content": "test content",
        "importance": 0.5,
        "source": "user",
        "create_at": now,
        "tags": [],
        "use_count": 0,
        "updated_at": now,
    }
    defaults.update(kwargs)
    return MemoryEntry(**defaults)


# ============ 6.1 启动链路测试 ============

class TestStartupChain:
    """测试启动链路：初始化记忆系统、加载记忆、构建系统提示"""

    def test_long_term_memory_load_empty(self):
        """加载不存在的文件返回空列表"""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = LongTermMemory(os.path.join(tmpdir, "nonexistent.md"))
            entries = memory.load()
            assert entries == []

    def test_long_term_memory_save_and_load(self):
        """保存后再加载，数据不丢失"""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "MEMORY.md")
            memory = LongTermMemory(filepath)

            entry = _make_entry(id="test-1", content="Skywalker 使用四层记忆")
            memory.save([entry])

            loaded = memory.load()
            assert len(loaded) == 1
            assert loaded[0].content == "Skywalker 使用四层记忆"

    def test_long_term_memory_add_entry_dedup(self):
        """添加重复 ID 的条目会覆盖"""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "MEMORY.md")
            memory = LongTermMemory(filepath)

            entry1 = _make_entry(id="same-id", content="旧内容")
            entry2 = _make_entry(id="same-id", content="新内容")

            memory.add_entry(entry1)
            memory.add_entry(entry2)

            loaded = memory.load()
            assert len(loaded) == 1
            assert loaded[0].content == "新内容"

    def test_memory_manager_get_system_context(self):
        """测试系统上下文注入，用户级 > 项目级"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "MEMORY.md")
            user_path = os.path.join(tmpdir, "USER.md")

            project_memory = LongTermMemory(project_path)
            user_memory = LongTermMemory(user_path)

            # 保存项目记忆
            project_memory.save([_make_entry(id="p1", content="项目记忆内容")])
            # 保存用户记忆
            user_memory.save([_make_entry(id="u1", content="用户偏好内容")])

            compressor = FakeCompressor()
            manager = MemoryManager(project_memory, user_memory, compressor)

            context = manager.get_system_context()
            assert "用户偏好内容" in context
            assert "项目记忆内容" in context
            # 用户级在前
            assert context.index("用户偏好内容") < context.index("项目记忆内容")

    def test_conversation_manager_init(self):
        """测试 ConversationManager 初始化"""
        compressor = FakeCompressor()
        conv = ConversationManager(compressor=compressor, max_tokens=1000)

        assert conv.messages == []
        assert conv.total_tokens == 0


# ============ 6.2 对话中链路测试 ============

class TestConversationChain:
    """测试对话中链路：消息追加、token 计算、压缩触发"""

    def test_add_message_increments_tokens(self):
        """追加消息后 token 数增加"""
        compressor = FakeCompressor()
        conv = ConversationManager(compressor=compressor, max_tokens=1000)

        msg = Message(Role.USER, "你好世界")
        conv.add_message(msg)

        assert len(conv.messages) == 1
        assert conv.total_tokens > 0

    def test_should_compress_false_when_under_threshold(self):
        """token 未超限时不触发压缩"""
        compressor = FakeCompressor()
        conv = ConversationManager(
            compressor=compressor,
            max_tokens=1000,
            compress_threshold=0.75,
        )

        conv.add_message(Message(Role.USER, "短消息"))
        assert conv.should_compress() is False

    def test_should_compress_true_when_over_threshold(self):
        """token 超限时触发压缩"""
        compressor = FakeCompressor()
        conv = ConversationManager(
            compressor=compressor,
            max_tokens=50,  # 很小的限制
            compress_threshold=0.75,
        )

        # 添加足够多的消息使 token 超限
        for i in range(10):
            conv.add_message(Message(Role.USER, f"第{i}条消息内容足够长"))

        assert conv.should_compress() is True

    def test_compress_reduces_messages(self):
        """压缩后消息数减少"""
        compressor = FakeCompressor()
        conv = ConversationManager(
            compressor=compressor,
            max_tokens=50,
            compress_threshold=0.5,
        )

        # 添加多条消息
        for i in range(10):
            conv.add_message(Message(Role.USER, f"消息{i}"))

        original_count = len(conv.messages)
        asyncio.run(conv.compress())

        assert len(conv.messages) < original_count

    def test_compress_inserts_summary_message(self):
        """压缩后插入 [SUMMARY] 标记的系统消息"""
        compressor = FakeCompressor()
        conv = ConversationManager(
            compressor=compressor,
            max_tokens=50,
            compress_threshold=0.5,
        )

        for i in range(10):
            conv.add_message(Message(Role.USER, f"消息{i}"))

        asyncio.run(conv.compress())

        summary_msgs = [m for m in conv.messages if "[SUMMARY]" in m.content]
        assert len(summary_msgs) >= 1

    def test_compress_preserves_system_messages(self):
        """压缩保留 system 消息"""
        compressor = FakeCompressor()
        conv = ConversationManager(
            compressor=compressor,
            max_tokens=50,
            compress_threshold=0.5,
        )

        conv.add_message(Message(Role.SYSTEM, "系统提示"))
        for i in range(10):
            conv.add_message(Message(Role.USER, f"消息{i}"))

        asyncio.run(conv.compress())

        system_msgs = [m for m in conv.messages if m.role == Role.SYSTEM]
        assert len(system_msgs) >= 1


# ============ 6.3 退出链路测试 ============

class TestShutdownChain:
    """测试退出链路：on_shutdown 写回记忆"""

    def test_on_shutdown_writes_to_project_memory(self):
        """on_shutdown 将摘要写入项目记忆"""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "MEMORY.md")
            project_memory = LongTermMemory(filepath)
            user_memory = LongTermMemory(os.path.join(tmpdir, "USER.md"))

            compressor = FakeCompressor()
            manager = MemoryManager(project_memory, user_memory, compressor)

            state = AgentState()
            state.messages.append(Message(Role.USER, "你好"))
            state.messages.append(Message(Role.ASSISTANT, "你好！"))

            asyncio.run(manager.on_shutdown(state))

            entries = project_memory.load()
            assert len(entries) == 1
            assert "摘要" in entries[0].content
            assert entries[0].source == "session"

    def test_on_shutdown_skips_empty_state(self):
        """空状态不写入记忆"""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "MEMORY.md")
            project_memory = LongTermMemory(filepath)
            user_memory = LongTermMemory(os.path.join(tmpdir, "USER.md"))

            compressor = FakeCompressor()
            manager = MemoryManager(project_memory, user_memory, compressor)

            state = AgentState()  # 空消息列表
            asyncio.run(manager.on_shutdown(state))

            entries = project_memory.load()
            assert len(entries) == 0


# ============ 端到端测试 ============

class TestEndToEnd:
    """端到端测试：模拟完整对话流程"""

    def test_full_conversation_flow(self):
        """模拟完整对话：启动 → 对话 → 退出"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 6.1 启动链路
            project_path = os.path.join(tmpdir, "MEMORY.md")
            user_path = os.path.join(tmpdir, "USER.md")

            project_memory = LongTermMemory(project_path)
            user_memory = LongTermMemory(user_path)

            # 预置一些记忆
            project_memory.save([_make_entry(id="p1", content="项目上下文")])
            user_memory.save([_make_entry(id="u1", content="用户偏好")])

            compressor = FakeCompressor()
            manager = MemoryManager(project_memory, user_memory, compressor)
            conv = ConversationManager(compressor=compressor, max_tokens=1000)

            # 构建系统提示
            system_context = manager.get_system_context()
            assert "项目上下文" in system_context
            assert "用户偏好" in system_context

            # 6.2 对话中链路
            user_msg = Message(Role.USER, "你好")
            conv.add_message(user_msg)

            # 模拟 LLM 回复
            assistant_msg = Message(Role.ASSISTANT, "你好！有什么可以帮助你的？")
            conv.add_message(assistant_msg)

            assert len(conv.messages) == 2
            assert conv.should_compress() is False

            # 6.3 退出链路
            state = AgentState()
            state.messages = conv.messages

            asyncio.run(manager.on_shutdown(state))

            # 验证记忆被写入（预置的 + 新添加的）
            entries = project_memory.load()
            assert len(entries) == 2
            session_entries = [e for e in entries if e.source == "session"]
            assert len(session_entries) == 1
            assert "摘要" in session_entries[0].content
