from __future__ import annotations
from math import e
import os
from pathlib import Path
from datetime import datetime, timezone
from skywalker.memory.base import MemoryEntry, MemoryType
from skywalker.memory.schema import parse_memory_md, serialize_memory_md
from skywalker.memory.search import search_entries
from skywalker.memory.short_term import LLMCompressor, CompressorBase, SubAgentCompressor


class LongTermMemory:
    """持久化记忆存储, 负责 读写 MEMORY.md 和USER.md"""
    def __init__(self, file_path: str, max_entries: int = 100):
        self._file_path = Path(os.path.expanduser(file_path))
        self._max_entries = max_entries
    def load(self) -> list[MemoryEntry]:
        """读取文件内容，调用 parse_memory_md 解析"""
        if not self._file_path.exists():
            return []
        context = self._file_path.read_text(encoding="utf-8")
        return parse_memory_md(context)
    
    def save(self, entries: list[MemoryEntry]) -> None:
        """保存记忆条目到文件，超过 max_entries 时截断低重要性条目"""
        # 按 importance 降序排列
        sorted_entries = sorted(entries, key=lambda e: e.importance, reverse=True)
        
        # 截断超出部分
        if len(sorted_entries) > self._max_entries:
            sorted_entries = sorted_entries[:self._max_entries]
        
        content = serialize_memory_md(sorted_entries)
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._file_path.write_text(content, encoding="utf-8")
    def add_entry(self, entry: MemoryEntry) -> None:
        """添加一条记忆条目"""
        entries = self.load()

        entries = [e for e in entries if e.id != entry.id] # 去重
        entries.append(entry)
        self.save(entries)


    def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """加载文件之后 执行关键词搜索"""
        entries = self.load()
        return search_entries(entries, query, top_k=top_k)


    
class MemoryManager:
    """管理项目级和用户级记忆"""
    def __init__(self, project_memory: LongTermMemory, user_memory: LongTermMemory,compressor):
        self._project_memory = project_memory
        self._user_memory = user_memory
        self._compressor = compressor
        
    async def on_shutdown(self, state) -> bool:
        """对话结束时, 提取关键信息并写记忆文件。返回是否实际保存了记忆。"""
        from skywalker.core import Message, Role

        if not state.messages:
            return False
        # 使用压缩器进行压缩
        try:
            summary = await self._compressor.compress(state.messages)
        except Exception:
            summary = None

        if not summary:
            return False
        now = datetime.now(timezone.utc)
        # 写入项目记忆
        project_entry = MemoryEntry(
            id = f"session-{now.strftime('%Y%m%d%H%M%S')}",
            type = MemoryType.FACT,
            content=summary,
            importance = 0.6,
            source = "session",
            create_at = now,
            updated_at=now,
            tags = ["session-summary"],
        )
        self._project_memory.add_entry(project_entry)
        return True
    def get_system_context(self) -> str:
        """合并项目记忆和用户记忆为系统提示文本
        注入优先级：用户级 > 项目级"""
        parts: list[str] = []
        # 用户级记忆
        user_entries = self._user_memory.load()
        if user_entries:
            user_texts = [e.content for e in user_entries]
            parts.append("用户偏好：\n" + "\n".join(f"- {t}" for t in user_texts))

        # 项目记忆
        project_entries = self._project_memory.load()
        if project_entries:
            project_texts = [e.content for e in project_entries[:5]]
            parts.append("项目记忆：\n" + "\n".join(f"- {t}" for t in project_texts))

        return "\n\n".join(parts)

