# skywalker/session/tool_log.py
"""工具调用日志，持久化到 session 目录"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class ToolCallRecord:
    """单次工具调用记录"""
    turn_index: int          # 第几轮对话
    tool_name: str
    tool_input: dict | None = None
    output: str = ""
    exit_code: int | None = None
    started_at: str = ""     # ISO 8601
    duration_ms: int = 0     # 耗时毫秒


class ToolLog:
    """工具调用日志管理"""

    def __init__(self, session_dir: str | Path):
        self._path = Path(session_dir) / "tool_log.json"
        self._records: list[ToolCallRecord] = []
        self._load()

    def _load(self):
        """从文件加载"""
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._records = [ToolCallRecord(**r) for r in data]
            except (json.JSONDecodeError, TypeError):
                self._records = []

    def _save(self):
        """保存到文件"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(r) for r in self._records]
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def append(self, record: ToolCallRecord):
        """添加一条记录并保存"""
        self._records.append(record)
        self._save()

    def get_all(self) -> list[ToolCallRecord]:
        """获取所有记录"""
        return self._records

    def get_by_turn(self, turn_index: int) -> list[ToolCallRecord]:
        """获取指定轮次的记录"""
        return [r for r in self._records if r.turn_index == turn_index]

    def clear(self):
        """清空日志"""
        self._records = []
        self._save()
