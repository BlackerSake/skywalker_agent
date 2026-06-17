from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from skywalker.session.manager import SessionManager
from skywalker.core import AgentState
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from skywalker.ui.picker import pick_session
from skywalker.core import Message

@dataclass
class CommandResult:
    """命令执行结果"""
    output: str
    should_complete: bool = True
    resumed_messages: list[Message] | None = None

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

        session_id = await pick_session(sessions)
        if session_id is None:
            return CommandResult(output="已取消")

        return await self._action(session_id, ctx)
