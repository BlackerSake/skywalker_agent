from __future__ import annotations

from dataclasses import dataclass
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.status import Status


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
        self._style_name = style  # "default" | "minimal"

        # 状态管理
        self._agent_buffer: str = ""  # 缓存完整回复
        self._last_tool_input: dict | None = None
        self._spinner_status: Status | None = None
        self._live: Live | None = None
        self._streaming_started: bool = False  # 是否已开始流式输出

    def render_event(self, event: StreamEvent) -> None:
        """根据事件类型分发渲染"""
        if isinstance(event, AgentTextStreaming):
            self._render_agent_text_streaming(event)
        elif isinstance(event, AgentTurnComplete):
            self._render_agent_turn_complete(event)
        elif isinstance(event, ToolExecutionStarted):
            self._stop_spinner()
            self._render_tool_execution_started(event)
        elif isinstance(event, ToolExecutionCompleted):
            self._render_tool_execution_completed(event)
        elif isinstance(event, CompactProgressEvent):
            self._stop_spinner()
            self._render_compact_progress_event(event)

    def _render_agent_text_streaming(self, event: AgentTextStreaming) -> None:
        """流式输出 Agent 回复"""
        # 首次收到文本时，停止 spinner，打印前缀
        if not self._streaming_started:
            self._stop_spinner()
            self._streaming_started = True
            self.console.print("Agent: ", end="", style="bold cyan")
            self.console.print("⎆ ", end="", style="cyan")

        # 逐字符输出，实现打字机效果
        self._agent_buffer += event.text
        self.console.print(event.text, end="", markup=False, highlight=False)

    def _render_agent_turn_complete(self, event: AgentTurnComplete) -> None:
        """Agent 回复完成"""
        # 换行
        self.console.print()

        # 重置状态
        self._agent_buffer = ""
        self._streaming_started = False

    def _render_tool_execution_started(self, event: ToolExecutionStarted) -> None:
        """工具开始执行"""
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
        """工具执行完成"""
        # exit_code 已经在工具输出中，不再重复打印

        if self._style_name == "default":
            self._render_tool_output(event.tool_name, self._last_tool_input, event.output)
        else:
            self.console.print(event.output)

        self._last_tool_input = None

    def _render_tool_output(self, tool_name: str, tool_input: dict | None, output: str) -> None:
        """工具输出差异化渲染"""
        lower = tool_name.lower()

        if lower in ("bash", "shell"):
            cmd = tool_input.get("command", "") if tool_input else ""
            self.console.print(Panel(output, title=f"Shell: {cmd}", border_style="blue"))

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
        """检测文本是否包含 Markdown 语法"""
        indicators = ["```", "## ", "### ", "- ", "* ", "1. ", "**", "__", "> "]
        return any(ind in text for ind in indicators)

    @staticmethod
    def _guess_lexer(file_path: str) -> str:
        """根据文件扩展名猜测语法高亮语言"""
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
        """生成工具输入的简短摘要"""
        if tool_name.lower() == "bash":
            return tool_input.get("command", "")
        elif tool_name.lower() in ("read", "fileread"):
            return f"file_path={tool_input.get('file_path', '')}"
        elif tool_name.lower() in ("edit", "fileedit"):
            return f"file_path={tool_input.get('file_path', '')}"
        return ""

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
