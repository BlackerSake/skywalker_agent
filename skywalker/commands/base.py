from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from skywalker.session.manager import SessionManager
from skywalker.core import AgentState
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.application import get_app
@dataclass
class CommandResult:
    """命令执行结果"""
    output: str
    should_complete: bool = True

class CommandBase(ABC):
    """所有命令的抽象基类"""
    name: str
    description: str
    usage: str  # 命令使用说明,例如"/resume [session_id]"

    @abstractmethod
    async def execute(self, state: AgentState, args: list[str]) -> CommandResult:
        """执行命令""" 
        ...


class SessionActionCommand(CommandBase):
    """需要交互式选择会话的 Command 基类"""

    def __init__(self, session_manager: SessionManager):
        self._sm = session_manager

    async def _action(self, session_id: str, ctx: AgentState) -> CommandResult:
        raise NotImplementedError

    async def execute(self, args: list[str], ctx: AgentState) -> CommandResult:
        if args:
            return await self._action(args[0], ctx)

        sessions = self._sm.list_sessions()
        if not sessions:
            return CommandResult(output="没有历史会话")

        session_id = await self._pick(sessions)
        if session_id is None:
            return CommandResult(output="已取消")

        return await self._action(session_id, ctx)

    async def _pick(self, sessions: list) -> str | None:

        current = [0]

        def render():
            lines = ["\n历史会话（↑↓ 切换，回车确认，ESC/q 取消，或直接输入 session_id）：\n"]
            for i, s in enumerate(sessions):
                prefix = " > " if i == current[0] else "   "
                row = f"{prefix}{s.title}  ({s.message_count} 条)"
                lines.append(f"\033[7m{row}\033[0m" if i == current[0] else row)
            print("\033[2J\033[H" + "\n".join(lines), end="", flush=True)

        render()
        kb = KeyBindings()

        @kb.add("up")
        def _up(event):
            current[0] = (current[0] - 1) % len(sessions)
            render()

        @kb.add("down")
        def _down(event):
            current[0] = (current[0] + 1) % len(sessions)
            render()

        @kb.add("escape")
        @kb.add("q")
        def _cancel(event):
            event.app.exit(result=None)

        @kb.add("enter")
        def _confirm(event):
            buf = event.app.current_buffer.text.strip()
            event.app.exit(result=buf if buf else sessions[current[0]].session_id)

        ps = PromptSession(
            key_bindings=kb,
            completer=WordCompleter([s.session_id for s in sessions], ignore_case=True),
        )
        try:
            return await ps.prompt_async(HTML("<ansigreen>session_id:</ansigreen> "))
        except (EOFError, KeyboardInterrupt):
            return None