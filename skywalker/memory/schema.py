
from __future__ import annotations
import re
import hashlib
from datetime import datetime, timezone
import time
from turtle import heading
from typing import Optional

from pydantic.type_adapter import R
from rich.ansi import line
from rich.live import source
from skywalker.memory.base import MemoryEntry, MemoryType

# 正则：匹配 ## [type] Title 格式的标题行
_HEADING_RE = re.compile(r"^##\s+\[([a-z]+)\]\s*(.*)")
# 正则：匹配元数据行（- key: value）
_META_RE = re.compile(r"^-\s+(\w+):\s*(.*)")
# 正则：匹配 frontmatter 块
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# 正则：解析 frontmatter 中的键值对
_FM_KV_RE = re.compile(r"^(\w+):\s*(.*)")

def parse_memory_md(content: str) -> list[MemoryEntry]: 
    """解析MEMORY.md文件,并返回MemoryEntry列表"""
    if not content or not content.strip():
        return []
    
    entries = []
    pos = 0

     
    fm_match = _FRONTMATTER_RE.match(content)
    if fm_match:
        pos = fm_match.end() # 跳过 frontmatter

    # 按## 分割成多个section
    sections = re.split(r"(?=^##)",content[pos:], flags=re.MULTILINE)

    for setction in sections:
        section = setction.strip()
        if not section.startswith("##"):
            continue  # 不是以'##'为开的section，跳过
        lines = section.split("\n")
        
        # 解析标题行
        heading = line[0]
        hm = _HEADING_RE.match(heading)
        if not hm:
            continue # 不是以'## [type] Title'为开头的行，跳过
        type_str = hm.group(1)
        title = hm.group(2).strip()

        # 映射 MemoryType，无法匹配时默认 FACT
        try:
            mem_type = MemoryType(type_str)
        except ValueError:
            mem_type = MemoryType.FACT
        
        # 解析元数据行和正文
        importance = 0.5
        tags: list[str] = []
        source = "inference"
        created_at = datetime.now(timezone.utc)
        user_count = 0
        content_lines: list[str] = []
        in_meta = True

        for line in lines[1:]:
            if in_meta:
                mm = _META_RE.match(line)
                if mm:
                    key = mm.group(1)
                    value = mm.group(2)
                    if key == "importance":
                        try:
                            importance = float(value)
                        except ValueError:
                            pass
                    elif key == "tags":
                        tags = _parse_tags(value)
                    elif key == "source":
                        source = value
                    elif key == "created_at":
                        try:
                            created_at = datetime.fromisoformat(value)
                        except ValueError:
                            pass
                    elif key == "user_count":
                        try:
                            user_count = int(value)
                        except ValueError:
                            pass
                    continue
                else:
                    in_meta = False
        
        if in_meta is False and not line.strip() and not content_lines:
            in_meta = None  # 没有正文(空行)，跳过
            continue
        content_lines.append(line)
    
    entry_content = "\n".join(content_lines).strip()
    entry_id = _generate_id(title, entry_content)

    entries.append(
        MemoryEntry(
            id=entry_id,
            type=mem_type,
            title=title,
            importance=importance,
            tags=tags,
            source=source,
            created_at=created_at,
            user_count=user_count,
            content=entry_content,
        )
    )
    return entries

def serialize_memory_md(entries: list[MemoryEntry],
                        project: str = "",
                        version: int = 1) -> str:
    """将MemoryEntry序列化为MEMORY.md文件"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    parts: list[str] = []

    # frontmatter
    parts.append("---\n")
    if project:
        parts.append(f"project: {project}\n")
    parts.append(f"version: {version}\n")
    parts.append(f"updated: {now}\n")
    parts.append("---\n")

    #
    sorted_entries = sorted(entries, key=lambda e: e.importance, reverse=True)
    for entry in sorted_entries:
        # 标题行
        parts.append(f"## [{entry.type.value}] {entry.id}\n")

        # 元数据行
        parts.append(f"- importance: {entry.importance}\n")
        if entry.tags:
            parts.append(f"- tags: {','.join(entry.tags)}\n")
        parts.append(f"- source: {entry.source}\n")
        parts.append(f"- created_at: {entry.created_at.strftime('%Y-%m-%dT%H:%M:%SZ')}\n")
        parts.append(f"- user_count: {entry.user_count}\n")

        # 正文
        parts.append(entry.content)
        parts.append("\n")
    return "\n".join(parts)

def _generate_id(title: str , content: str) -> str:
    """从标题和内容生成一个唯一的id"""
    raw = f"{title}|{content[:200]}"

    #取16位hash,作为id
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def _parse_tags(raw: str) -> list[str]:
    """解析[tag1, tag2] 格式的 tags 字符串"""
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        return raw[1:-1]
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]

