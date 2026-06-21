
"""通用全屏列表浏览器（状态机：列表 ↔ 详情）"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from rich.console import Console

if TYPE_CHECKING:
    from skywalker.session.tool_log import ToolCallRecord


@dataclass
class ListItem:
    """列表项"""
    id: str
    title: str
    subtitle: str = ""
    detail: str = ""           # 详情内容（支持多行）
    detail_lines: list[str] | None = None  # 预解析的详情行（用于滚动）
    metadata: dict | None = None

    @classmethod
    def from_tool_record(cls, record: ToolCallRecord) -> "ListItem":
        """从 ToolCallRecord 创建 ListItem"""
        action_desc = cls._get_action_desc(record)
        detail = cls._get_detail(record)

        return cls(
            id=f"{record.tool_name}_{record.turn_index}",
            title=f"[Turn {record.turn_index}] {record.tool_name}",
            subtitle=f"  {action_desc}" if action_desc else "",
            detail=detail,
        )

    @staticmethod
    def _get_action_desc(record: ToolCallRecord) -> str:
        """获取操作描述"""
        if not record.tool_input:
            return ""

        tool_lower = record.tool_name.lower()

        if tool_lower in ("bash", "shell"):
            cmd = record.tool_input.get("command", "")
            return cmd[:50] + ("..." if len(cmd) > 50 else "")

        if tool_lower == "file":
            action = record.tool_input.get("action", "")
            path = record.tool_input.get("path", "")
            if action == "read_file":
                return f"read {path}"
            elif action == "write_file":
                return f"write {path}"
            elif action == "list_dir":
                return f"list {path}"
            return f"{action} {path}"

        if tool_lower in ("read", "fileread"):
            return f"read {record.tool_input.get('file_path', '')}"

        if tool_lower in ("edit", "fileedit"):
            return f"edit {record.tool_input.get('file_path', '')}"

        if tool_lower == "web":
            return record.tool_input.get("url", "")[:50]

        for v in record.tool_input.values():
            if isinstance(v, str):
                return v[:50]
        return ""

    @staticmethod
    def _get_detail(record: ToolCallRecord) -> str:
        """获取详情文本"""
        parts = []
        action = ListItem._get_action_desc(record)
        if action:
            parts.append(f"操作: {action}")
        if record.tool_input:
            parts.append(f"参数: {record.tool_input}")
        if record.duration_ms:
            parts.append(f"耗时: {record.duration_ms}ms")
        if record.exit_code is not None:
            parts.append(f"exit_code: {record.exit_code}")
        parts.append("")
        parts.append("输出:")
        parts.append(record.output)
        return "\n".join(parts)


class ListBrowser:
    """全屏列表浏览器"""

    STATE_LIST = "list"
    STATE_DETAIL = "detail"

    def __init__(self, console: Console):
        self._console = console
        self._selected: int = 0
        self._detail_scroll: int = 0
        self._state: str = self.STATE_LIST

    def run(
        self,
        items: list[ListItem],
        title: str = "列表",
        on_select: Callable[[ListItem], None] | None = None,
    ) -> ListItem | None:
        """
        进入全屏浏览器

        Args:
            items: 列表项
            title: 标题
            on_select: 选中回调（可选）

        Returns:
            选中的项，ESC 返回 None
        """
        if not items:
            self._console.print("[dim]暂无记录[/]")
            return None

        self._selected = len(items) - 1
        self._state = self.STATE_LIST

        with self._console.screen():
            while True:
                if self._state == self.STATE_LIST:
                    result = self._run_list(items, title)
                    if result == "exit":
                        return None
                    elif result == "enter":
                        item = items[self._selected]
                        # 如果有详情，进入详情状态
                        if item.detail or item.detail_lines:
                            self._state = self.STATE_DETAIL
                            self._detail_scroll = 0
                        else:
                            # 没有详情，直接返回
                            if on_select:
                                on_select(item)
                            return item
                elif self._state == self.STATE_DETAIL:
                    result = self._run_detail(items[self._selected])
                    if result == "back":
                        self._state = self.STATE_LIST
                    elif result == "select":
                        item = items[self._selected]
                        if on_select:
                            on_select(item)
                        return item

    def _run_list(self, items: list[ListItem], title: str) -> str:
        """列表状态"""
        self._render_list(items, title)
        key = self._read_key()

        if key == "esc":
            return "exit"
        elif key == "up":
            self._selected = max(0, self._selected - 1)
        elif key == "down":
            self._selected = min(len(items) - 1, self._selected + 1)
        elif key == "enter":
            return "enter"
        return ""

    def _run_detail(self, item: ListItem) -> str:
        """详情状态"""
        lines = item.detail_lines or item.detail.splitlines()
        max_scroll = max(0, len(lines) - 20)

        self._render_detail(item, lines)
        key = self._read_key()

        if key == "esc":
            return "back"
        elif key == "up":
            self._detail_scroll = max(0, self._detail_scroll - 1)
        elif key == "down":
            self._detail_scroll = min(max_scroll, self._detail_scroll + 1)
        elif key == "enter":
            return "select"
        return ""

    def _render_list(self, items: list[ListItem], title: str):
        """渲染列表界面"""
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

            prefix = "▶ " if selected else "  "
            subtitle = f"  {item.subtitle}" if item.subtitle else ""
            line = f"{prefix}{item.title}{subtitle}"
            self._console.print(line, style=style)

        # 底部
        self._console.print("─" * 60, style="dim")
        self._console.print()
        has_detail = any(item.detail or item.detail_lines for item in items)
        if has_detail:
            self._console.print("[dim]↑↓ 移动  Enter 查看详情  Esc 退出[/]")
        else:
            self._console.print("[dim]↑↓ 移动  Enter 确认  Esc 退出[/]")

    def _render_detail(self, item: ListItem, lines: list[str]):
        """渲染详情界面（支持滚动）"""
        self._console.clear()

        self._console.print(
            f" {item.title}                          Esc 返回列表",
            style="bold white on blue",
        )
        self._console.print("─" * 60, style="dim")

        # 副标题（输入信息）
        if item.subtitle:
            self._console.print(f"  {item.subtitle}", style="dim")
            self._console.print("─" * 60, style="dim")

        # 检测是否是 diff 格式
        detail_text = item.detail or ""
        if detail_text.startswith("---") or detail_text.startswith("diff"):
            from skywalker.ui.diff_renderer import render_diff
            render_diff(self._console, detail_text)
        else:
            # 普通内容（带滚动）
            visible_lines = lines[self._detail_scroll:self._detail_scroll + 20]
            for line in visible_lines:
                self._console.print(line)

        # 底部
        self._console.print("─" * 60, style="dim")
        scroll_info = f"[{self._detail_scroll + 1}/{len(lines)}]" if len(lines) > 20 else ""
        self._console.print(f"[dim]↑↓ 滚动  Enter 确认  Esc 返回列表 {scroll_info}[/]")

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
            ch = os.read(fd, 1).decode("utf-8", errors="ignore")

            if ch == "\x1b":
                if select.select([fd], [], [], 0.2)[0]:
                    rest = os.read(fd, 10).decode("utf-8", errors="ignore")
                    if rest.startswith("[A") or rest.startswith("OA"):
                        return "up"
                    elif rest.startswith("[B") or rest.startswith("OB"):
                        return "down"
                else:
                    return "esc"
            elif ch == "\r" or ch == "\n":
                return "enter"
            elif ch == "\x0f":
                return "esc"
            return ""
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
