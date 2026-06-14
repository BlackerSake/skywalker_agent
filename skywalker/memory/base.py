from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MemoryType(Enum):
    FACT = "fact"  # 事实
    PREFERENCE = "preference"  # 偏好
    ARCHITECTURE = "architecture"  # 架构
    BUGFIX = "bugfix"  # bug修复

@dataclass
class MemoryEntry:
    id: str
    type: MemoryType
    content: str
    importance: float # 0.0-1.0
    source: str  #记录记忆来源
    create_at: datetime
    tags: list[str] = field(default_factory=list)
    use_count: int = 0
    updated_at: datetime | None = None

class MemoryStore(ABC):
    @abstractmethod
    def add(self, entry: MemoryEntry) -> None: 
        """添加一条记忆，id 重复时覆盖"""
        ...


    @abstractmethod
    def get(self, id: str) -> MemoryEntry | None: 
        """按 id 获取记忆，不存在返回 None"""
        ...
    
    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]: 
        """按关键词搜索，返回相关性降序排列的结果"""
        ...

    @abstractmethod
    def delete(self, id: str) -> bool: 
        """删除一条记忆，返回是否成功（id 不存在返回 False）"""
        ...






