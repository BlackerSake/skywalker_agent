# skywalker/ui/tool_browser.py
"""Ctrl+O 全屏工具调用浏览器"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from skywalker.session.tool_log import ToolCallRecord, ToolLog


class ToolBrowser:
    """全屏工具调用浏览器"""

    def __init__(self, console: Console):
        self._console = console
        self._selected: int = 0  # 当前选中索引
        self._expanded: bool = False  # 是否展开详情

    def run(self, log: ToolLog):
        """进入全屏浏览器"""
        records = log.get_all()
        if not records:
            self._console.print("[dim]暂无工具调用记录[/]")
            return

        self._selected = len(records) - 1  # 默认选中最后一条

        with self._console.screen():
            while True:
                self._render(records)
                key = self._read_key()

                if key == "esc":
                    break
                elif key == "up":
                    self._selected = max(0, self._selected - 1)
                    self._expanded = False
                elif key == "down":
                    self._selected = min(len(records) - 1, self._selected + 1)
                    self._expanded = False
                elif key == "enter":
                    self._expanded = not self._expanded

    def _render(self, records: list[ToolCallRecord]):
        """渲染浏览器界面"""
        self._console.clear()

        # 标题
        self._console.print(
            " 工具调用记录 — 当前会话                          Esc 返回",
            style="bold white on blue",
        )
        self._console.print("─" * 60, style="dim")

        # 列表
        for i, record in enumerate(records):
            selected = (i == self._selected)
            style = "bold white on dark_green" if selected else ""

            # 时间标签
            turn_tag = f"[Turn {record.turn_index}]"

            # 工具名
            tool_name = record.tool_name.ljust(8)

            # 输入摘要
            summary = self._summarize_input(record.tool_name, record.tool_input)

            # 耗时
            duration = f"{record.duration_ms}ms" if record.duration_ms else ""

            # 行内容
            prefix = "▶ " if selected else "  "
            line = f"{prefix}{turn_tag} {tool_name} {summary[:30]:<30} {duration:>8}"

            self._console.print(line, style=style)

        # 分隔线
        self._console.print("─" * 60, style="dim")

        # 展开详情
        if self._expanded and 0 <= self._selected < len(records):
            record = records[self._selected]
            self._render_detail(record)

        # 底部提示
        self._console.print()
        self._console.print(
            "[dim]↑↓ 移动  Enter 展开/折叠  Esc 退出[/]",
        )

    def _render_detail(self, record: ToolCallRecord):
        """渲染工具详情"""
        lower = record.tool_name.lower()

        self._console.print()
        self._console.print(f"  输入: {record.tool_input}", style="dim")
        self._console.print()

        if lower in ("bash", "shell"):
            self._console.print(record.output, style="dim")
        elif lower in ("read", "fileread"):
            file_path = record.tool_input.get("file_path", "") if record.tool_input else ""
            lexer = self._guess_lexer(file_path)
            output = record.output[:2000] + "\n... (truncated)" if len(record.output) > 2000 else record.output
            self._console.print(Syntax(output, lexer, theme="monokai"))
        elif lower in ("edit", "fileedit"):
            self._console.print(Panel(record.output, title="Edit", border_style="green"))
        else:
            output = record.output[:1000] + "\n... (truncated)" if len(record.output) > 1000 else record.output
            self._console.print(output)

        if record.exit_code is not None:
            style = "green" if record.exit_code == 0 else "red"
            self._console.print(f"  exit_code: {record.exit_code}", style=style)

    @staticmethod
    def _summarize_input(tool_name: str, tool_input: dict | None) -> str:
        """生成输入摘要"""
        if not tool_input:
            return ""
        if tool_name.lower() in ("bash", "shell"):
            return tool_input.get("command", "")
        elif tool_name.lower() in ("read", "fileread"):
            return tool_input.get("file_path", "")
        elif tool_name.lower() in ("edit", "fileedit"):
            return tool_input.get("file_path", "")
        return ""

    @staticmethod
    def _guess_lexer(file_path: str) -> str:
        """猜测语法高亮语言"""
        ext_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".json": "json", ".yaml": "yaml", ".yml": "yaml",
            ".md": "markdown", ".html": "html", ".css": "css",
            ".sh": "bash", ".sql": "sql",
        }
        for ext, lexer in ext_map.items():
            if file_path.endswith(ext):
                return lexer
        return "text"

    def _read_key(self) -> str:
        """读取按键"""
        import os
        import select
        import sys
        import termios
        import tty

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
