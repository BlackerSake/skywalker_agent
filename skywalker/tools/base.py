from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class DiffHunk:
    """Diff 变更块"""
    old_start: int
    new_start: int
    lines: list[tuple[str, str]]   # ("+"/"-"/" ", content)


@dataclass
class FileDiff:
    """结构化 Diff 对象"""
    path: str
    is_new_file: bool
    additions: int
    deletions: int
    hunks: list[DiffHunk]

    def to_unified_text(self, context_lines: int = 3) -> str:
        """转换为 unified diff 文本（用于 Syntax 渲染）"""
        import difflib

        # 从 hunks 重建 unified diff
        lines = []
        lines.append(f"--- a/{self.path}")
        lines.append(f"+++ b/{self.path}")

        for hunk in self.hunks:
            old_count = sum(1 for prefix, _ in hunk.lines if prefix != "+")
            new_count = sum(1 for prefix, _ in hunk.lines if prefix != "-")
            lines.append(f"@@ -{hunk.old_start},{old_count} +{hunk.new_start},{new_count} @@")
            for prefix, content in hunk.lines:
                lines.append(f"{prefix}{content}")

        return "\n".join(lines)


@dataclass
class ToolResult:
    """工具执行结果"""
    tool_call_id: str
    output: str
    truncated: bool = False
    diff: FileDiff | list[FileDiff] | None = None   # 结构化 diff，给渲染层用


@dataclass
class ToolError:
    tool_call_id: str
    error: str
    reason: Literal["denied", "timeout", "user_rejected", "execution_error"]


class ToolBase(ABC):
    name: str
    description: str
    parameters: dict  # JSON Schema

    @abstractmethod
    async def execute(self, arguments: dict) -> ToolResult | ToolError:
        ...

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

