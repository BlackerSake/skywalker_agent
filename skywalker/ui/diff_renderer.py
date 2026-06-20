
"""Diff 渲染器 将 Unified diff 渲染为红绿色"""

from __future__ import annotations

from rich.console import Console
from rich.text import Text


def render_diff(console: Console, diff_text: str):
    """渲染 unified diff，红绿色显示，带行号和统计

    Args:
        console: Rich Console 实例
        diff_text: unified diff 格式的文本
    """
    lines = diff_text.splitlines()

    # 统计新增/删除行数
    added = sum(1 for line in lines if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in lines if line.startswith("-") and not line.startswith("---"))

    # 渲染统计信息
    stats = []
    if added > 0:
        stats.append(f"[green]+{added}[/]")
    if removed > 0:
        stats.append(f"[red]-{removed}[/]")
    if stats:
        console.print(f"  {' '.join(stats)} lines changed")
        console.print()

    # 解析 @@ 行获取行号
    current_new_line = 0

    for line in lines:
        text = Text()

        if line.startswith("+++") or line.startswith("---"):
            # 文件名：粗体
            text.append(line, style="bold")

        elif line.startswith("@@"):
            # 行号标记：青色，解析新文件行号
            text.append(line, style="cyan")
            # 解析 @@ -a,b +c,d @@ 中的 c
            import re
            match = re.search(r"\+(\d+)", line)
            if match:
                current_new_line = int(match.group(1))

        elif line.startswith("+"):
            # 新增行：绿色，带行号
            text.append(f"{current_new_line:>4} ", style="dim")
            text.append(line, style="green")
            current_new_line += 1

        elif line.startswith("-"):
            # 删除行：红色
            text.append("    ", style="dim")
            text.append(line, style="red")

        else:
            # 普通行: 灰色,带行号
            text.append(f"{current_new_line:>4} ", style="dim")
            text.append(line, style="grey58")
            current_new_line += 1

        console.print(text)


