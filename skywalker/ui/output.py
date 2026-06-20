
"""Agent 文本流式输出渲染器"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from rich.console import Console
from rich.markdown import Markdown
from rich.status import Status
from skywalker.ui.tool_panel import ToolPanel

@dataclass
class StreamEvent:
    """流式事件基类"""
    pass

@dataclass
class AgentTextStreaming(StreamEvent):
    """Agent 流式文本增量"""
    text: str

@dataclass
class AgentTurnComplete(StreamEvent):
    """Agent 回复完成"""
    full_text: str

@dataclass
class ToolExecutionStarted(StreamEvent):
    """工具开始执行"""
    tool_name: str
    tool_input: dict | None = None

@dataclass
class ToolExecutionCompleted(StreamEvent):
    """工具执行完成"""
    tool_name: str
    output: str
    exit_code: int | None = None

@dataclass
class CompactProgressEvent(StreamEvent):
    """压缩进度提示"""
    message: str


class OutputRenderer:
    """Agent 文本流式输出渲染器"""

    def __init__(self, style: str = "default"):
        self.console = Console()
        self._style_name = style  # "default" | "minimal"

        # 状态管理
        self._agent_buffer: str = ""  # 缓存完整回复
        self._spinner_status: Status | None = None
        self._streaming_started: bool = False  # 是否已开始流式输出

        # 工具子界面（外部注入）
        self._tool_panel: ToolPanel | None = None

    def set_tool_panel(self, panel):
        """注入工具子界面"""
        self._tool_panel = panel

    def render_event(self, event: StreamEvent) -> None:
        """根据事件类型分发渲染"""
        if isinstance(event, AgentTextStreaming):
            self._render_agent_text_streaming(event)

        elif isinstance(event, AgentTurnComplete):
            self._render_agent_turn_complete(event)

        elif isinstance(event, ToolExecutionStarted):
            self._stop_spinner()
            if self._tool_panel:
                self._tool_panel.open(
                    tool_id=event.tool_name,
                    tool_name=event.tool_name,
                    tool_input=event.tool_input,
                )

        elif isinstance(event, ToolExecutionCompleted):
            if self._tool_panel:
                self._tool_panel.close(tool_id=event.tool_name)

        elif isinstance(event, CompactProgressEvent):
            self._stop_spinner()
            self.console.print(f"[dim]{event.message}[/dim]")

    def _render_agent_text_streaming(self, event: AgentTextStreaming) -> None:
        """流式输出 Agent 回复"""
        # 首次收到文本时，停止 spinner，关闭工具子界面，保存光标位置
        if not self._streaming_started:
            self._stop_spinner()
            self._streaming_started = True

            # 关闭工具子界面，打印摘要
            if self._tool_panel:
                summary = self._tool_panel.close_all()
                if summary:
                    from rich.text import Text
                    self.console.print(Text(f"  ⏵ {summary}", style="dim"))

            # 保存光标位置（在 "Agent: " 之前）
            self._save_cursor_position()
            self.console.print("Agent: ", end="", style="bold cyan")
            self.console.print("⎆ ", end="", style="cyan")

        # 流式输出
        self._agent_buffer += event.text
        self.console.print(event.text, end="", markup=False, highlight=False)

    def _render_agent_turn_complete(self, event: AgentTurnComplete) -> None:
        """Agent 回复完成 → 用 MD 重新渲染"""
        # 恢复光标位置
        self._restore_cursor_position()
        # 清除从光标到屏幕末尾
        self._clear_from_cursor()

        # 重新打印带 MD 渲染的内容
        self.console.print("Agent: ", end="", style="bold cyan")
        self.console.print("⎆ ", end="", style="cyan")
        self.console.print(Markdown(self._agent_buffer))

        # 重置
        self._agent_buffer = ""
        self._streaming_started = False


    @staticmethod
    def _save_cursor_position():
        """保存光标位置"""
        sys.stdout.write("\033[s")
        sys.stdout.flush()

    @staticmethod
    def _restore_cursor_position():
        """恢复光标位置"""
        sys.stdout.write("\033[u")
        sys.stdout.flush()

    @staticmethod
    def _clear_from_cursor():
        """从光标位置开始清除屏幕"""
        sys.stdout.write("\033[J")
        sys.stdout.flush()


    def show_thinking(self) -> None:
        """显示 Thinking Spinner"""
        if self._style_name == "default":
            self._spinner_status = self.console.status(
                "[cyan]Thinking...[/cyan]", spinner="dots"
            )
            self._spinner_status.start()

    def _stop_spinner(self) -> None:
        """停止 Spinner"""
        if self._spinner_status:
            self._spinner_status.stop()
            self._spinner_status = None

    def set_style(self, style_name: str) -> None:
        """切换渲染风格"""
        self._style_name = style_name
