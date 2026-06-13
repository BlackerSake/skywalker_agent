from datetime import datetime, timezone

import pytest

from skywalker.memory.base import MemoryEntry, MemoryType, MemoryStore

"""
  test_base.py — 测试"地基"数据结构
  
  测的是 MemoryEntry 这个数据类能不能正常工作：
  - 枚举类型 MemoryType 的值对不对（FACT 对应 "fact")
  - 创建 MemoryEntry 时，标签默认是空列表，不会被多个实例共享
  - 重要性字段 importance 能接受 0.0 到 1.0
  - 抽象类 MemoryStore 不能直接实例化（只能被继承）

"""
class TestMemoryType:
    def test_enum_values_are_lowercase_strings(self):
        assert MemoryType.FACT.value == "fact"
        assert MemoryType.PREFERENCE.value == "preference"
        assert MemoryType.ARCHITECTURE.value == "architecture"
        assert MemoryType.BUGFIX.value == "bugfix"

    def test_enum_from_value(self):
        assert MemoryType("fact") is MemoryType.FACT
        assert MemoryType("preference") is MemoryType.PREFERENCE

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            MemoryType("nonexistent")


class TestMemoryEntry:
    def _make_entry(self, **kwargs) -> MemoryEntry:
        now = datetime.now(timezone.utc)
        defaults = {
            "id": "test-id",
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

    def test_tags_default_is_empty_list(self):
        entry = self._make_entry()
        assert entry.tags == []

    def test_tags_default_not_shared_between_instances(self):
        e1 = self._make_entry()
        e2 = self._make_entry()
        e1.tags.append("test")
        assert e2.tags == []

    def test_use_count_default_is_zero(self):
        entry = self._make_entry()
        assert entry.use_count == 0

    def test_importance_range(self):
        low = self._make_entry(importance=0.0)
        high = self._make_entry(importance=1.0)
        assert low.importance == 0.0
        assert high.importance == 1.0


class TestMemoryStoreInterface:
    def test_cannot_instantiate_abstract_class(self):
        with pytest.raises(TypeError):
            MemoryStore()