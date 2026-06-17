"""记忆命令单元测试"""
import pytest
from unittest.mock import MagicMock, AsyncMock
from skywalker.commands.builtin.memory import MemoryCommand
from skywalker.commands.base import CommandResult
from skywalker.memory.base import MemoryEntry, MemoryType
from skywalker.core import AgentState
from datetime import datetime, timezone


@pytest.fixture
def mock_memory_manager():
    """创建模拟的 MemoryManager"""
    manager = MagicMock()

    # 模拟项目记忆
    project_entries = [
        MemoryEntry(
            id="entry-1",
            type=MemoryType.FACT,
            content="Skywalker 是一个 CLI Agent Runtime",
            importance=0.8,
            source="session",
            create_at=datetime.now(timezone.utc),
            tags=["project"],
        ),
        MemoryEntry(
            id="entry-2",
            type=MemoryType.PREFERENCE,
            content="用户喜欢简洁的回答",
            importance=0.7,
            source="user",
            create_at=datetime.now(timezone.utc),
            tags=["preference"],
        ),
    ]

    # 模拟用户记忆
    user_entries = [
        MemoryEntry(
            id="user-1",
            type=MemoryType.PREFERENCE,
            content="用户是高级开发者",
            importance=0.9,
            source="user",
            create_at=datetime.now(timezone.utc),
            tags=["user"],
        )
    ]

    manager._project_memory.load.return_value = project_entries
    manager._user_memory.load.return_value = user_entries
    manager._project_memory.search.return_value = project_entries[:1]
    manager._project_memory.save.return_value = None

    return manager


@pytest.fixture
def agent_state():
    """创建 AgentState"""
    return AgentState(project_root="/test")


class TestMemoryCommand:
    """MemoryCommand 测试"""

    @pytest.mark.asyncio
    async def test_memory_list(self, mock_memory_manager, agent_state):
        """测试 /memory list"""
        cmd = MemoryCommand(mock_memory_manager)
        result = await cmd.execute(["list"], agent_state)

        assert "项目记忆" in result.output
        assert "用户记忆" in result.output
        assert "Skywalker" in result.output
        assert "高级开发者" in result.output

    @pytest.mark.asyncio
    async def test_memory_search(self, mock_memory_manager, agent_state):
        """测试 /memory search"""
        cmd = MemoryCommand(mock_memory_manager)
        result = await cmd.execute(["search", "Skywalker"], agent_state)

        assert "搜索结果" in result.output
        mock_memory_manager._project_memory.search.assert_called_once_with("Skywalker", top_k=5)

    @pytest.mark.asyncio
    async def test_memory_search_no_query(self, mock_memory_manager, agent_state):
        """测试 /memory search 无查询词"""
        cmd = MemoryCommand(mock_memory_manager)
        result = await cmd.execute(["search"], agent_state)

        assert "用法" in result.output

    @pytest.mark.asyncio
    async def test_memory_search_no_results(self, mock_memory_manager, agent_state):
        """测试 /memory search 无结果"""
        mock_memory_manager._project_memory.search.return_value = []

        cmd = MemoryCommand(mock_memory_manager)
        result = await cmd.execute(["search", "不存在的内容"], agent_state)

        assert "未找到" in result.output

    @pytest.mark.asyncio
    async def test_memory_clear(self, mock_memory_manager, agent_state):
        """测试 /memory clear"""
        cmd = MemoryCommand(mock_memory_manager)
        result = await cmd.execute(["clear"], agent_state)

        assert "已清空" in result.output
        mock_memory_manager._project_memory.save.assert_called_once_with([])

    @pytest.mark.asyncio
    async def test_memory_no_subcommand(self, mock_memory_manager, agent_state):
        """测试 /memory 无子命令"""
        cmd = MemoryCommand(mock_memory_manager)
        result = await cmd.execute([], agent_state)

        assert "用法" in result.output

    @pytest.mark.asyncio
    async def test_memory_unknown_subcommand(self, mock_memory_manager, agent_state):
        """测试 /memory 未知子命令"""
        cmd = MemoryCommand(mock_memory_manager)
        result = await cmd.execute(["unknown"], agent_state)

        assert "未知子命令" in result.output
