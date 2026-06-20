
"""通用全屏列表浏览器"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable

from rich.console import Console
from rich.table import Table

@dataclass
class ListItem:
    """列表项"""
    id: str
    title: str
    subtitle: str = ""
    detail: str = ""
    metadata: dict | None = None


class ListBrowser:
    """全屏列表调用浏览器"""

    def __init__(self, console: Console):
        self._console = console
        self._selected: int = 0  # 当前选中索引
        self._expanded: bool = False  # 是否展开详情

    def run(self, items: list[ListItem], title: str = "列表",
            on_select: Callable[[ListItem], None] | None = None) -> ListItem | None:
        """进入全屏浏览器"""
        if not items:
            self._console.print("[dim]暂无调用记录[/]")
            return None

        self._selected = len(items) - 1  # 默认选中最后一条

        with self._console.screen():
            while True:
                self._render(items, title)
                key = self._read_key()

                if key == "esc":
                    break
                elif key == "up":
                    self._selected = max(0, self._selected - 1)
                    self._expanded = False
                elif key == "down":
                    self._selected = min(len(items) - 1, self._selected + 1)
                    self._expanded = False
                elif key == "enter":
                    self._expanded = items[self._selected]
                    if on_select:
                        on_select(self._expanded)
                    return self._expanded

    def _render(self, items: list[ListItem], title: str):
        """渲染浏览器界面"""
        self._console.clear()

        # 标题
        self._console.print(
            f" {title}                          Esc 返回",
            style="bold white on blue",
        )
        self._console.print("─" * 60, style="dim")

        # 列表
        for i, item in enumerate(items):
            selected = (i == self._selected)
            style = "bold white on dark_green" if selected else ""

            # 行内容
            prefix = "▶ " if selected else "  "
            subtitle = f"{item.subtitle}" if item.subtitle else ""
            line = f"{prefix}{item.title}{subtitle}"

            self._console.print(line, style=style)

        # 分隔线
        self._console.print("─" * 60, style="dim")

        # 展开详情
        if self._expanded and 0 <= self._selected < len(items):
            item = items[self._selected]
            if item.detail:
                self._console.print()
                self._console.print(item.detail)

        # 底部提示
        self._console.print()
        self._console.print("[dim]↑↓ 移动  Enter 展开/折叠  Esc 退出[/]")

    def _read_key(self) -> str:
        """读取按键"""
        import select
        import sys
        import termios
        import tty
        import os

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)

            # 读取第一个字节
            ch = os.read(fd, 1).decode("utf-8", errors="ignore")

            if ch == "\x1b":
                # ESC 序列：用 select 检查是否有后续字节
                if select.select([fd], [], [], 0.2)[0]:
                    # 读取后续字节
                    rest = os.read(fd, 10).decode("utf-8", errors="ignore")
                    if rest.startswith("[A") or rest.startswith("OA"):
                        return "up"
                    elif rest.startswith("[B") or rest.startswith("OB"):
                        return "down"
                else:
                    # 无后续 → 单独 ESC
                    return "esc"

            elif ch == "\r" or ch == "\n":
                return "enter"
            elif ch == "\x0f":  # Ctrl+O
                return "esc"
            return ""
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        




