

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from skywalker.memory.base import MemoryEntry

# 正则：匹配 ASCII 单词（3字符以上）或单个汉字
_TOKEN_RE = re.compile(r"[a-zA-Z0-9]{3,}|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    """将文本拆分为 token 列表"""
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def score_entry(entry: MemoryEntry, 
                query_tokens: list[str],
                now: datetime | None = None) -> float:
    """计算单条记忆的得分"""
    if not query_tokens:
        return 0.0
    if now is None:
        now = datetime.now(timezone.utc)
    
    # 构建 meta tokens (tags + type)
    meta_text = " ".join(entry.tags) + " " + entry.type.value
    meta_tokens = tokenize(meta_text)

    meta_hits = sum(1 for t in meta_tokens if t in query_tokens)
    meta_hits = meta_hits * 2.0

    # 构建 content tokens
    content_tokens = tokenize(entry.content)
    content_hits = sum(1 for t in query_tokens if t in content_tokens)

    # 如果没有匹配，返回 0
    if meta_hits == 0 and content_hits == 0:
        return 0.0

    # 重要性权重得分
    importance_score = entry.importance * 0.4

    # 使用频率
    use_score = min(entry.use_count / 10, 0.5)

    # 时间权重得分
    recency_boost = 0.0
    if entry.updated_at:
        age = now - entry.updated_at
        if age < timedelta(days=14):
            recency_boost = 0.3
        elif age < timedelta(days=30):
            recency_boost = 0.1
    return meta_hits + content_hits + importance_score + use_score + recency_boost


def search_entries(entries: list[MemoryEntry],
                   query: str,
                   top_k: int = 5
                   ) -> list[MemoryEntry]:
    """对记忆列表执行关键词搜索，返回排序后的结果"""
    if not query.strip():
        return []

    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    now = datetime.now(timezone.utc)

    scored: list[tuple[float, MemoryEntry]] = []
    for entry in entries:
        s = score_entry(entry, query_tokens, now)
        if s > 0:
            scored.append((s, entry))
            entry.use_count += 1  # 副作用：命中计数 +1

    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:top_k]]
