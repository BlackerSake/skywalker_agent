from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
from skywalker.core import Message, Role
from skywalker.memory.base import MemoryEntry
from skywalker.memory.schema import parse_memory_md, serialize_memory_md
import logging

@dataclass
class SessionMeta:
    session_id: str
    title: str
    created_at: str
    updated_at: str
    project_root: str
    summary: str = ""
    message_count: int = 0

class SessionStore:
    """负责单个会话的磁盘 I/O，只做文件操作，不管生命周期"""
    def __init__(self, base_dir: str = "/Alpha/College_new/skywalker_agent/.skywalker/sessions"):
        self._base_dir = Path(os.path.expanduser(base_dir))

    def create_session_dir(self, session_id: str) -> Path:
        """创建一个会话的目录，返回目录路径"""
        session_dir = self._base_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir
    
    def save_meta(self, session_id: str, meta: SessionMeta) -> None:
        """将 会话元数据 保存到 文件"""
        path = self._base_dir / session_id / "meta.json"
        path.write_text(
            json.dumps(meta.__dict__, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def load_meta(self, session_id: str) -> SessionMeta | None:
        """从文件加载 会话元数据,不存在就返回 None"""
        path = self._base_dir / session_id / "meta.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return SessionMeta(**data)
    
    def save_messages(self, session_id: str, messages: list[Message]) -> None:
        """将 会话消息 保存到 文件"""
        path = self._base_dir / session_id / "messages.json"
        data = [
            {
                "role": m.role.value,
                "content": m.content,
                "tool_call_id": m.tool_call_id,
            }
            for m in messages
        ]
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    
    def load_messages(self, session_id: str) -> list[Message]:
        """从文件加载会话消息，不存在返回空列表"""
        path = self._base_dir / session_id / "messages.json"
        if not path.exists():
            logging.warning(f"Session {session_id} not found")
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return [
            Message(
                role=Role(item["role"]),
                content=item["content"],
                tool_call_id=item.get("tool_call_id"),
            )
            for item in data
        ]
    
    def list_sessions(self) -> list[SessionMeta]:
        """列出所有会话,时间倒序"""
        sessions = []
        if not self._base_dir.exists():
            return sessions
        for path in sorted(self._base_dir.iterdir(), reverse=True):
            meta_path = path / "meta.json"
            if path.is_dir() and meta_path.exists():
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                sessions.append(SessionMeta(**data))
        return sessions
    
    def delete_session(self, session_id: str) -> None:
        """删除一个会话"""
        session_dir = self._base_dir / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir)
            return True
        return False
    
    def save_session_memory(self, session_id: str, memory: list[MemoryEntry]) -> None:
        """将 会话内存 保存到 文件"""
        path = self._base_dir / session_id / "memory.md"
        path.write_text(
            serialize_memory_md(memory),
            encoding="utf-8"
        )
        






