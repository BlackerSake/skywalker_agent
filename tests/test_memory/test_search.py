
from datetime import datetime, timedelta, timezone

import pytest

from skywalker.memory.base import MemoryEntry, MemoryType
from skywalker.memory.search import tokenize, score_entry, search_entries

"""
核心测试场景：

空索引返回空列表
单条目精确匹配
多条目按得分排序
中文分词（汉字逐字拆分）
英文短词过滤（< 3 字符被忽略）
时效加成：14天内的条目得分高于 30天前的条目
use_count 上限为 5
"""


def _make_entry(**kwargs) -> MemoryEntry:
    now = datetime.now(timezone.utc)
    defaults = {
        "id": "test-id",
        "type": MemoryType.FACT,
        "content": "test content",
        "importance": 0.5,
        "source": "user",
        "created_at": now,
        "updated_at": now,
        "tags": [],
        "use_count": 0,
    }
    defaults.update(kwargs)
    return MemoryEntry(**defaults)


class TestTokenize:
    def test_english_words(self):
        tokens = tokenize("Hello World Python")
        assert tokens == ["hello", "world", "python"]

    def test_short_words_filtered(self):
        tokens = tokenize("I am a Go dev")
        # "I" (1字符), "am" (2字符), "a" (1字符), "Go" (2字符) 被过滤
        assert tokens == ["dev"]

    def test_chinese_chars(self):
        tokens = tokenize("记忆系统")
        assert tokens == ["记", "忆", "系", "统"]

    def test_mixed_chinese_english(self):
        tokens = tokenize("Memory记忆系统")
        assert "memory" in tokens
        assert "记" in tokens
        assert "忆" in tokens

    def test_empty_string(self):
        assert tokenize("") == []

    def test_numbers_included_if_3chars(self):
        tokens = tokenize("abc 123 x")
        assert "abc" in tokens
        assert "123" in tokens
        assert "x" not in tokens


class TestScoreEntry:
    def test_no_query_tokens_returns_zero(self):
        entry = _make_entry()
        assert score_entry(entry, []) == 0.0

    def test_meta_hits_weight(self):
        entry = _make_entry(tags=["architecture"], type=MemoryType.ARCHITECTURE)
        tokens = ["architecture"]
        score = score_entry(entry, tokens)
        # meta_hits = 2 (tag "architecture" + type value "architecture")
        # 2 * 2.0 = 4.0, plus importance 0.5 * 0.4 = 0.2
        assert score >= 4.0

    def test_body_hits(self):
        entry = _make_entry(content="Skywalker uses memory system")
        tokens = ["skywalker"]
        score = score_entry(entry, tokens)
        # body_hits = 1
        assert score >= 1.0

    def test_recency_boost_14_days(self):
        now = datetime.now(timezone.utc)
        recent = _make_entry(updated_at=now - timedelta(days=5))
        old = _make_entry(updated_at=now - timedelta(days=40))
        tokens = ["test"]
        score_recent = score_entry(recent, tokens, now=now)
        score_old = score_entry(old, tokens, now=now)
        # recent 应比 old 多 0.3 的时效加成
        assert score_recent > score_old

    def test_recency_boost_30_days(self):
        now = datetime.now(timezone.utc)
        entry = _make_entry(updated_at=now - timedelta(days=20))
        tokens = ["test"]
        score = score_entry(entry, tokens, now=now)
        # 20天在 14~30 天区间，应有 0.1 加成
        base = 0.5 * 0.4  # importance only
        assert score >= base + 0.1

    def test_use_count_capped_at_5(self):
        entry_high = _make_entry(use_count=10)
        entry_cap = _make_entry(use_count=5)
        tokens = ["test"]
        score_high = score_entry(entry_high, tokens)
        score_cap = score_entry(entry_cap, tokens)
        # use_count 超过 5 时得分应相同
        assert abs(score_high - score_cap) < 0.01


class TestSearchEntries:
    def test_empty_query_returns_empty(self):
        entries = [_make_entry(content="hello world")]
        assert search_entries(entries, "") == []
        assert search_entries(entries, "   ") == []

    def test_empty_entries_returns_empty(self):
        assert search_entries([], "query") == []

    def test_single_match(self):
        entry = _make_entry(content="Skywalker agent runtime")
        results = search_entries([entry], "skywalker")
        assert len(results) == 1
        assert results[0].id == entry.id

    def test_multiple_entries_ranked(self):
        high = _make_entry(
            id="high",
            content="Python memory management",
            importance=0.9,
        )
        low = _make_entry(
            id="low",
            content="Unrelated content",
            importance=0.1,
        )
        results = search_entries([high, low], "python memory")
        assert len(results) == 2
        # high 应排在前面
        assert results[0].id == "high"

    def test_top_k_limits_results(self):
        entries = [_make_entry(id=f"e{i}", content=f"test {i}") for i in range(10)]
        results = search_entries(entries, "test", top_k=3)
        assert len(results) == 3

    def test_use_count_incremented(self):
        entry = _make_entry(content="searchable content")
        assert entry.use_count == 0
        search_entries([entry], "searchable")
        assert entry.use_count == 1

    def test_no_match_returns_empty(self):
        entry = _make_entry(content="hello world")
        results = search_entries([entry], "xyz123")
        assert len(results) == 0