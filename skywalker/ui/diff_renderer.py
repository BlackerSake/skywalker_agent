# skywalker/ui/diff_renderer.py
"""Diff 渲染器，使用 Rich Syntax 渲染结构化 FileDiff"""

from __future__ import annotations

from rich.console import Console
from rich.syntax import Syntax

from skywalker.tools.base import FileDiff


def render_file_diff(console: Console, diff: FileDiff, context_lines: int = 3):
    """渲染 FileDiff 对象

    Args:
        console: Rich Console 实例
        diff: 结构化 FileDiff 对象
        context_lines: 上下文行数（已由 difflib 控制，此处保留用于未来扩展）
    """
    if diff.is_new_file:
        console.print(f"    # {diff.path} (新建, {diff.additions} 行)", style="dim green")
        return

    # 文件名 + 变更统计
    console.print(f"    # {diff.path} (+{diff.additions} -{diff.deletions})", style="dim")

    # 转换为 unified diff 文本
    diff_text = diff.to_unified_text(context_lines)

    # 用 Syntax 渲染（Pygments 内置 diff lexer，自动处理红绿配色）
    console.print(Syntax(diff_text, "diff", theme="monokai", line_numbers=False))
