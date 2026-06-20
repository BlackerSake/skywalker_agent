# skywalker/ui/diff_clip.py
"""Diff 片段截取与渲染（上下各 N 行，缩进显示）"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rich.console import Console
from rich.text import Text


@dataclass
class DiffLine:
    """Diff 行"""
    line_no: int | None  # 新文件行号（删除行为 None）
    content: str         # 原始内容（含 +/-/空格前缀）
    type: str            # "add", "del", "context"


def parse_diff(diff_text: str) -> list[DiffLine]:
    """解析 unified diff，返回带行号的行列表"""
    lines = diff_text.splitlines()
    result = []
    current_line = 0

    for line in lines:
        if line.startswith("@@"):
            # 解析 @@ -a,b +c,d @@ 中的 c
            match = re.search(r"\+(\d+)", line)
            if match:
                current_line = int(match.group(1))
            result.append(DiffLine(line_no=None, content=line, type="header"))
        elif line.startswith("+++") or line.startswith("---"):
            result.append(DiffLine(line_no=None, content=line, type="file"))
        elif line.startswith("+"):
            result.append(DiffLine(line_no=current_line, content=line, type="add"))
            current_line += 1
        elif line.startswith("-"):
            result.append(DiffLine(line_no=None, content=line, type="del"))
        else:
            result.append(DiffLine(line_no=current_line, content=line, type="context"))
            current_line += 1

    return result


def clip_diff(diff_lines: list[DiffLine], context: int = 3) -> list[DiffLine]:
    """截取变更行及其上下文"""
    # 找到所有变更行的索引
    change_indices = [
        i for i, line in enumerate(diff_lines)
        if line.type in ("add", "del")
    ]

    if not change_indices:
        return []

    # 扩展上下文
    include = set()
    for idx in change_indices:
        for j in range(max(0, idx - context), min(len(diff_lines), idx + context + 1)):
            include.add(j)

    # 按顺序返回
    return [diff_lines[i] for i in sorted(include)]


def render_diff_clip(console: Console, diff_text: str, context_lines: int = 3):
    """渲染 diff 片段（上下各 N 行），缩进 4 空格显示

    Args:
        console: Rich Console 实例
        diff_text: unified diff 格式的文本
        context_lines: 上下文行数
    """
    diff_lines = parse_diff(diff_text)
    clipped = clip_diff(diff_lines, context=context_lines)

    if not clipped:
        return

    # 统计
    added = sum(1 for line in clipped if line.type == "add")
    removed = sum(1 for line in clipped if line.type == "del")

    # 渲染
    text = Text()
    text.append("    ")  # 缩进 4 空格

    for line in clipped:
        if line.type == "header":
            # @@ 行：青色
            text.append(line.content, style="cyan")
            text.append("\n")
            text.append("    ")
        elif line.type == "file":
            # 文件名：跳过
            continue
        elif line.type == "add":
            # 新增行：绿色，带行号
            no = f"{line.line_no:>3} " if line.line_no else "    "
            text.append(no, style="dim")
            text.append(line.content, style="green")
            text.append("\n")
            text.append("    ")
        elif line.type == "del":
            # 删除行：红色
            text.append("    ", style="dim")
            text.append(line.content, style="red")
            text.append("\n")
            text.append("    ")
        elif line.type == "context":
            # 上下文行：灰色，带行号
            no = f"{line.line_no:>3} " if line.line_no else "    "
            text.append(no, style="dim")
            text.append(line.content, style="grey58")
            text.append("\n")
            text.append("    ")

    console.print(text)
