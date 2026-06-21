
"""Diff 渲染器，使用 Rich Syntax 渲染结构化 FileDiff"""

from __future__ import annotations

from rich.console import Console
from rich.syntax import Syntax

from skywalker.tools.base import FileDiff


MAX_RENDER_LINES = 200
def render_file_diff(console: Console, 
                     diff: FileDiff | list[FileDiff] | None, 
                     max_lines: int = MAX_RENDER_LINES):
    """渲染 FileDiff 对象（支持单个或多个）

    Args:
        console: Rich Console 实例
        diff: 结构化 FileDiff 对象或列表
        context_lines: 上下文行数（已由 difflib 控制，此处保留用于未来扩展）
    """
    # 空值处理
    if diff is None:
        return
    
    # 列表: 逐个渲染, 中间添加分隔符
    if isinstance(diff, list):
        if not diff:
            return
        for i, d in enumerate(diff):
            if i > 0:
                console.print()
            _render_single(console, d, max_lines)
        return
    
    # 单个: 渲染
    _render_single(console, diff, max_lines)

def _render_single(console: Console, diff: FileDiff, max_lines: int):
    """渲染单个 FileDiff 对象"""
    try:
        # 标题行
        _render_title(console, diff)

        if not diff.hunks:
            console.print("    (无变更内容)", style="dim")
            return
        diff_text = diff.to_unified_text()

        # 按照行数进行截断
        text_lines = diff_text.splitlines()
        truncated = len(text_lines) > max_lines

        if truncated:
            diff_text = "\n".join(text_lines[:max_lines])

        # Syntax 渲染，monokai 主题有明显的红绿配色
        syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=True)
        console.print(syntax)

        # 截断提示
        if truncated:
            total = len(text_lines)
            console.print(f"    ...(已截断，共 {total} 行)", style="dim")
    except Exception as e:
        console.print(
            f"    # {diff.path} (+{diff.additions} -{diff.deletions}) "
            f"(渲染失败: {e})", style="dim red"
        )

def _render_title(console: Console, diff: FileDiff) -> None:
    """渲染 FileDiff 标题行"""
    if diff.is_new_file:
        line_count = sum(len(h.lines) for h in diff.hunks)
        console.print(
            f"    # {diff.path} (+{line_count} lines)",
            style="dim green"
        )
    else:
        console.print(
            f"    # {diff.path} (+{diff.additions} -{diff.deletions})",
            style="dim"
        )
