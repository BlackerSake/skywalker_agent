import asyncio
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from skywalker.memory.base import MemoryEntry, MemoryType
from skywalker.memory.long_term import LongTermMemory, MemoryManager
from skywalker.memory.short_term import CompressorBase


def _make_entry(id: str = "test-1", importance: float = 0.5, **kwargs) -> MemoryEntry:
    now = datetime.now(timezone.utc)
    defaults = {
        "id": id,
        "type": MemoryType.FACT,
        "content": f"content for {id}",
        "importance": importance,
        "source": "user",
        "create_at": now,
        "updated_at": now,
        "tags": [],
        "use_count": 0,
    }
    defaults.update(kwargs)
    return MemoryEntry(**defaults)


@pytest.fixture
def tmp_memory_path(tmp_path):
    return str(tmp_path / "MEMORY.md")


class TestLongTermMemoryLoad:
    def test_nonexistent_file_returns_empty(self, tmp_memory_path):
        ltm = LongTermMemory(tmp_memory_path)
        assert ltm.load() == []

    def test_load_after_save(self, tmp_memory_path):
        ltm = LongTermMemory(tmp_memory_path)
        entry = _make_entry()
        ltm.save([entry])
        loaded = ltm.load()
        assert len(loaded) == 1
        assert loaded[0].type == entry.type
        assert loaded[0].importance == entry.importance
        assert loaded[0].content == entry.content


class TestLongTermMemorySave:
    def test_save_creates_parent_dirs(self, tmp_path):
        nested = str(tmp_path / "a" / "b" / "MEMORY.md")
        ltm = LongTermMemory(nested)
        ltm.save([_make_entry()])
        assert Path(nested).exists()

    def test_save_sorted_by_importance_desc(self, tmp_memory_path):
        ltm = LongTermMemory(tmp_memory_path)
        low = _make_entry(id="low", importance=0.2)
        high = _make_entry(id="high", importance=0.9)
        ltm.save([low, high])
        loaded = ltm.load()
        assert loaded[0].importance >= loaded[1].importance

    def test_save_truncates_beyond_max_entries(self, tmp_memory_path):
        ltm = LongTermMemory(tmp_memory_path, max_entries=3)
        entries = [_make_entry(id=f"e{i}", importance=i * 0.1) for i in range(10)]
        ltm.save(entries)
        loaded = ltm.load()
        assert len(loaded) <= 3


class TestLongTermMemoryAddEntry:
    def test_add_entry_idempotent(self, tmp_memory_path):
        ltm = LongTermMemory(tmp_memory_path)
        entry = _make_entry(id="same-id")
        ltm.add_entry(entry)
        ltm.add_entry(entry)
        loaded = ltm.load()
        assert len(loaded) == 1

    def test_add_different_entries(self, tmp_memory_path):
        ltm = LongTermMemory(tmp_memory_path)
        ltm.add_entry(_make_entry(id="a"))
        ltm.add_entry(_make_entry(id="b"))
        loaded = ltm.load()
        assert len(loaded) == 2

    def test_add_updates_existing_entry(self, tmp_memory_path):
        ltm = LongTermMemory(tmp_memory_path)
        old = _make_entry(id="x", importance=0.3, content="old")
        new = _make_entry(id="x", importance=0.8, content="new")
        ltm.add_entry(old)
        ltm.add_entry(new)
        loaded = ltm.load()
        assert len(loaded) == 1
        assert loaded[0].content == "new"
        assert loaded[0].importance == 0.8


class TestLongTermMemorySearch:
    def test_search_returns_matching_entries(self, tmp_memory_path):
        ltm = LongTermMemory(tmp_memory_path)
        ltm.add_entry(_make_entry(id="match", content="Python memory management"))
        ltm.add_entry(_make_entry(id="no-match", content="unrelated"))
        results = ltm.search("python")
        assert any(r.id == "match" for r in results)

    def test_search_empty_file(self, tmp_memory_path):
        ltm = LongTermMemory(tmp_memory_path)
        assert ltm.search("query") == []


class StubCompressor(CompressorBase):
    async def compress(self, messages):
        return "shutdown summary"


class TestMemoryManager:
    def _make_state(self, messages=None):
        from unittest.mock import MagicMock
        state = MagicMock()
        state.messages = messages or []
        return state

    def test_on_shutdown_saves_summary(self, tmp_path):
        proj_path = str(tmp_path / "MEMORY.md")
        user_path = str(tmp_path / "USER.md")
        proj = LongTermMemory(proj_path)
        user = LongTermMemory(user_path)
        compressor = StubCompressor()
        manager = MemoryManager(proj, user, compressor)

        from skywalker.core import Message, Role
        state = self._make_state([
            Message(Role.USER, "hello"),
            Message(Role.ASSISTANT, "hi there"),
        ])

        loop = asyncio.new_event_loop()
        loop.run_until_complete(manager.on_shutdown(state))
        loop.close()

        loaded = proj.load()
        assert len(loaded) >= 1
        assert "shutdown summary" in loaded[0].content

    def test_on_shutdown_empty_messages_does_nothing(self, tmp_path):
        proj_path = str(tmp_path / "MEMORY.md")
        user_path = str(tmp_path / "USER.md")
        proj = LongTermMemory(proj_path)
        user = LongTermMemory(user_path)
        compressor = StubCompressor()
        manager = MemoryManager(proj, user, compressor)

        state = self._make_state([])
        loop = asyncio.new_event_loop()
        loop.run_until_complete(manager.on_shutdown(state))
        loop.close()

        assert proj.load() == []

    def test_get_system_context_merges_memories(self, tmp_path):
        proj_path = str(tmp_path / "MEMORY.md")
        user_path = str(tmp_path / "USER.md")
        proj = LongTermMemory(proj_path)
        user = LongTermMemory(user_path)
        compressor = StubCompressor()

        proj.add_entry(_make_entry(id="p1", content="project info"))
        user.add_entry(_make_entry(id="u1", content="user preference"))

        manager = MemoryManager(proj, user, compressor)
        context = manager.get_system_context()

        assert "project info" in context
        assert "user preference" in context

    def test_get_system_context_user_higher_priority(self, tmp_path):
        proj_path = str(tmp_path / "MEMORY.md")
        user_path = str(tmp_path / "USER.md")
        proj = LongTermMemory(proj_path)
        user = LongTermMemory(user_path)
        compressor = StubCompressor()

        proj.add_entry(_make_entry(id="p1", content="project info"))
        user.add_entry(_make_entry(id="u1", content="user preference"))

        manager = MemoryManager(proj, user, compressor)
        context = manager.get_system_context()

        # 用户记忆应出现在项目记忆之前
        user_pos = context.find("user preference")
        proj_pos = context.find("project info")
        assert user_pos < proj_pos