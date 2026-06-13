from datetime import datetime, timezone

import pytest

from skywalker.memory.base import MemoryEntry, MemoryType
from skywalker.memory.schema import parse_memory_md, serialize_memory_md

"""
核心测试场景：

有 frontmatter 时正确解析 project/version/updated
无 frontmatter 时从第一个 ##  开始解析
缺失字段（importance/tags/use_count）使用默认值
type 无法匹配 MemoryType 时默认 FACT
round-trip：parse(serialize(entries)) == entries

"""
def _make_entry(**kwargs) -> MemoryEntry:
    now = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    defaults = {
        "id": "abc123",
        "type": MemoryType.FACT,
        "content": "Skywalker uses four-layer memory.",
        "importance": 0.9,
        "source": "inference",
        "create_at": now,
        "tags": ["architecture", "memory"],
        "use_count": 3,
        "updated_at": now,
    }
    defaults.update(kwargs)
    return MemoryEntry(**defaults)


class TestParseMemoryMd:
    def test_empty_content_returns_empty_list(self):
        assert parse_memory_md("") == []
        assert parse_memory_md("   ") == []

    def test_with_frontmatter(self):
        content = """---
project: skywalker
version: 1
updated: 2026-06-01T10:00:00Z
---

## [fact] Test Entry
- importance: 0.8
- tags: [test]
- source: user
- create_at: 2026-06-01T10:00:00Z

Some content here.
"""
        entries = parse_memory_md(content)
        assert len(entries) == 1
        assert entries[0].type == MemoryType.FACT
        assert entries[0].importance == 0.8
        assert entries[0].tags == ["test"]
        assert entries[0].content == "Some content here."

    def test_without_frontmatter(self):
        content = """## [architecture] Design
- importance: 0.9
- tags: [arch]
- source: inference
- create_at: 2026-06-01T10:00:00Z

Architecture description.
"""
        entries = parse_memory_md(content)
        assert len(entries) == 1
        assert entries[0].type == MemoryType.ARCHITECTURE
        assert entries[0].content == "Architecture description."

    def test_missing_fields_use_defaults(self):
        content = """## [fact] Minimal
- source: user
- create_at: 2026-06-01T10:00:00Z

Just content.
"""
        entries = parse_memory_md(content)
        assert len(entries) == 1
        assert entries[0].importance == 0.5
        assert entries[0].tags == []

    def test_unknown_type_defaults_to_fact(self):
        content = """## [unknown] Something
- importance: 0.5
- source: user
- create_at: 2026-06-01T10:00:00Z

Content.
"""
        entries = parse_memory_md(content)
        assert len(entries) == 1
        assert entries[0].type == MemoryType.FACT

    def test_multiple_entries(self):
        content = """## [fact] First
- importance: 0.7
- source: user
- create_at: 2026-06-01T10:00:00Z

First content.

## [bugfix] Second
- importance: 0.3
- source: session
- create_at: 2026-06-02T10:00:00Z

Second content.
"""
        entries = parse_memory_md(content)
        assert len(entries) == 2
        assert entries[0].type == MemoryType.FACT
        assert entries[1].type == MemoryType.BUGFIX


class TestSerializeMemoryMd:
    def test_produces_valid_frontmatter(self):
        entry = _make_entry()
        result = serialize_memory_md([entry], project="skywalker", version=1)
        assert result.startswith("---\n")
        assert "project: skywalker" in result
        assert "version: 1" in result
        assert "updated:" in result

    def test_entries_sorted_by_importance_desc(self):
        low = _make_entry(id="low", importance=0.3, content="low")
        high = _make_entry(id="high", importance=0.9, content="high")
        result = serialize_memory_md([low, high])
        # high 应该出现在 low 之前
        pos_high = result.find("[fact] high")
        pos_low = result.find("[fact] low")
        assert pos_high < pos_low

    def test_empty_entries(self):
        result = serialize_memory_md([])
        assert "---" in result
        assert "##" not in result


class TestRoundTrip:
    def test_parse_serialize_round_trip(self):
        entry = _make_entry()
        serialized = serialize_memory_md([entry])
        parsed = parse_memory_md(serialized)
        assert len(parsed) == 1
        assert parsed[0].type == entry.type
        assert parsed[0].importance == entry.importance
        assert parsed[0].tags == entry.tags
        assert parsed[0].source == entry.source
        assert parsed[0].content == entry.content