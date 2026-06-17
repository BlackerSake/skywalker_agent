from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.status import Status
from typing import Literal

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
    """输出渲染器"""
    def __init__(self, style: str = "default"):
        self.console = Console()
        self._style_name = style  # "default" | "minimal" 渲染风格,全功能或纯文本

        # 状态管理
        self._agent_buffer: str = ""  # 缓存完整回复
        self._agent_line_open: bool = False  # 是否正在输出 agent 行
        self._last_tool_input: dict | None = None  # 最近一次工具输入
        self._spinner_status: Status | None = None  # Spinner 状态

    def render_event(self, event: StreamEvent) -> None:
        """根据事件类型 分发渲染"""
        if isinstance(event, AgentTextStreaming):
            self._render_agent_text_streaming(event)

        elif isinstance(event, AgentTurnComplete):
            self._render_agent_turn_complete(event)

        elif isinstance(event, ToolExecutionStarted):
            self._render_tool_execution_started(event)

        elif isinstance(event, ToolExecutionCompleted):
            self._render_tool_execution_completed(event)

        elif isinstance(event, CompactProgressEvent):
            self._render_compact_progress_event(event)

    def _render_agent_text_streaming(self, event: AgentTextStreaming) -> None:
        """流式输出 agent 回复"""
        if not self._agent_line_open:
            # 首次输出, 打印 ⎆ 作为前缀 
            self.console.print("⎆ ", end="", style="cyan")
            self._agent_line_open = True
        self._agent_buffer += event.text
        # 逐字打印 agent 输出
        self.console.print(event.text, end="", markup=False, highlight=False)
    


    def _render_agent_turn_complete(self, event: AgentTurnComplete) -> None:
        """输出 agent 回复完成"""
        if self._agent_line_open:
            self.console.print() # 打印换行符
            self._agent_line_open = False
        # 检测markdown语法
        if self._style_name == "default" and self._has_markdown(self._agent_buffer):
            self.console.print(Markdown(self._agent_buffer))
        self._agent_buffer = "" # 清空缓存

    def _render_tool_execution_started(self, event: ToolExecutionStarted) -> None:
        """tool 开始执行"""
        self._last_tool_input = event.tool_input
        self.console.print(f"  ⏵ {event.tool_name}", style="yellow", end="")

        if event.tool_input:
            summary = self._summarize_tool_input(event.tool_name, event.tool_input)
            if summary:
                self.console.print(f"  {summary}", style="dim")
            else:
                self.console.print()
        else:
            self.console.print()
        
    def _render_tool_execution_completed(self, event: ToolExecutionCompleted) -> None:
        """tool 执行完成"""
        if event.exit_code is not None:
            self.console.print(f"    exit_code: {event.exit_code}", style="dim")

        if self._style_name == "default":
            self._render_tool_output(event.tool_name, self._last_tool_input, event.output)
        else:
            self.console.print(event.output)

        self._last_tool_input = None
    def _render_tool_output(self, tool_name: str, tool_input: dict | None, output: str) -> None:
        """tool 输出 的差异化 的渲染"""
        lower = tool_name.lower()

        if lower == "bash":
            cmd = tool_input.get("command", "") if tool_input else ""
            self.console.print(Panel(output, title=f"Bash: {cmd}", border_style="blue"))

        elif lower in ("read", "fileread"):
            file_path = tool_input.get("file_path", "") if tool_input else ""
            lexer = self._guess_lexer(file_path)
            if len(output) > 2000:
                output = output[:2000] + "\n... (truncated)"
            self.console.print(Syntax(output, lexer, theme="monokai"))

        elif lower in ("edit", "fileedit"):
            self.console.print(Panel(output, title="Edit", border_style="green"))

        else:
            if len(output) > 1000:
                output = output[:1000] + "\n... (truncated)"
            self.console.print(output)

    def _render_compact_progress_event(self, event: CompactProgressEvent) -> None:
        """压缩进度提示"""
        self.console.print(f"[dim]{event.message}[/dim]")


    @staticmethod
    def _has_markdown(text: str) -> bool:
        """判断字符串是否包含 markdown 语法"""
        indicators = ["```", "## ", "### ", "- ", "* ", "1. ", "**", "__", "> "]
        return any(ind in text for ind in indicators)
    @staticmethod
    def _guess_lexer(file_path: str) -> str:
        """根据文件的扩展名 猜测代码语言"""
        ext_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".jsx": "jsx", ".tsx": "tsx", ".rs": "rust", ".go": "go",
            ".java": "java", ".c": "c", ".cpp": "cpp", ".h": "c",
            ".rb": "ruby", ".php": "php", ".sh": "bash", ".yaml": "yaml",
            ".yml": "yaml", ".json": "json", ".md": "markdown",
            ".html": "html", ".css": "css", ".sql": "sql",
        }
        for ext, lexer in ext_map.items():
            if file_path.endswith(ext):
                return lexer
        return "text"
    @staticmethod
    def _summarize_tool_input(tool_name: str, tool_input: dict) -> str:
        """根据工具输入 生成摘要"""
        if tool_name.lower() == "bash":
            return tool_input.get("command", "")
        elif tool_name.lower() in ("read", "fileread"):
            return f"file_path={tool_input.get('file_path', '')}"
        elif tool_name.lower() in ("edit", "fileedit"):
            return f"file_path={tool_input.get('file_path', '')}"
        return ""

    def show_thinking(self) -> None:
        """显示思考中 Thinking Spinner"""
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