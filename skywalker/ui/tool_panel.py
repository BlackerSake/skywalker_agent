
"""工具执行子界面，执行中实时显示进度"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from rich.console import Console
from rich.live import Live
from rich.table import Table


@dataclass
class ToolState:
    """单个工具的执行状态"""
    tool_name: str
    tool_input: dict | None = None
    finished: bool = False


class ToolPanel:
    """工具执行子界面（执行中实时显示）"""

    def __init__(self, console: Console):
        self._console = console
        self._live: Live | None = None
        self._tools: dict[str, ToolState] = {}

    def open(self, tool_id: str, tool_name: str, tool_input: dict | None = None):
        """开始显示工具执行详情"""
        self._tools[tool_id] = ToolState(
            tool_name=tool_name,
            tool_input=tool_input,
        )

        # 首个工具启动时创建 Live
        if self._live is None:
            self._live = Live(
                self._build_content(),
                console=self._console,
                refresh_per_second=10,
            )
            self._live.start()
        else:
            self._live.update(self._build_content())

    def close(self, tool_id: str):
        """关闭单个工具"""
        if tool_id in self._tools:
            self._tools[tool_id].finished = True
            if self._live:
                self._live.update(self._build_content())

    def close_all(self) -> str:
        """关闭所有工具，返回摘要行"""
        if self._live:
            self._live.stop()
            self._live = None

        # 生成摘要
        names = [s.tool_name for s in self._tools.values()]
        self._tools.clear()

        if not names:
            return ""

        counts = Counter(names)
        parts = [f"{name} x {n}" if n > 1 else name for name, n in counts.items()]
        return f"调用了 {len(names)} 个工具 ({'，'.join(parts)}) (ctrl + o 展开)"

    def _build_content(self) -> Table:
        """构建 Live 显示内容"""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="yellow")
        table.add_column()

        for state in self._tools.values():
            status = "✓" if state.finished else "..."
            summary = self._summarize_input(state.tool_name, state.tool_input)
            table.add_row(
                f"⏵ {state.tool_name}",
                f"{summary} ({status})"
            )

        return table

    @staticmethod
    def _summarize_input(tool_name: str, tool_input: dict | None) -> str:
        """生成工具输入摘要"""
        if not tool_input:
            return ""
        if tool_name.lower() in ("bash", "shell"):
            return tool_input.get("command", "")
        elif tool_name.lower() in ("read", "fileread"):
            return tool_input.get("file_path", "")
        elif tool_name.lower() in ("edit", "fileedit"):
            return tool_input.get("file_path", "")
        return ""
