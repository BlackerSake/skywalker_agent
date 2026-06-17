from __future__ import annotations

from skywalker.commands.base import CommandBase, CommandResult, SessionActionCommand
from skywalker.core import AgentState
from skywalker.session.manager import SessionManager

class SaveCommand(CommandBase):
    """手动保存当前会话(用于调试,正常流程会自动触发)"""

    name = "save"
    description = "手动保存当前会话"
    usage = "/save"
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    async def execute(self, args: list[str], ctx: AgentState) -> CommandResult:
        """保存当前会话"""
        title = " ".join(args) if args else None
        meta = await self.session_manager.save(title=title)
        return CommandResult(output=f"保存成功：{meta.session_id} ({meta.title})")

class ListCommand(CommandBase):
    """列出所有会话"""

    name = "list"
    description = "列出所有会话"
    usage = "/list"
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    async def execute(self, args: list[dict], ctx: AgentState) -> CommandResult:
        """列出所有会话"""
        sessions = self.session_manager.list_sessions()
        if not sessions:
            return CommandResult(output="没有历史会话")
        lines = ["历史会话:"]
        for s in sessions[:10]:
            lines.append(f"{s.session_id} {s.title} , ({s.message_count} 条消息)")
        return CommandResult(output="\n".join(lines))

class RenameCommand(CommandBase):
    """重命名当前会话"""

    name = "rename"
    description = "重命名当前会话"
    usage = "/rename <new_name> "
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
    async def execute(self, args: list[str], ctx: AgentState) -> CommandResult:
        """重命名当前会话"""
        if not args:
            return CommandResult(output="用法: /rename <new_name>")
        session_id = self.session_manager.current_session_id
        if not session_id:
            return CommandResult(output="当前没有会话")
        new_title = " ".join(args)
        # 直接操作 store，不经过 SessionManager
        store = self.session_manager._store
        meta = store.load_meta(session_id)
        if meta is None:
            return CommandResult(output=f"会话 {session_id} 不存在")
        meta.title = new_title
        store.save_meta(session_id, meta)
        return CommandResult(output=f"会话 {session_id} 已重命名为 {new_title}")

class ResumeCommand(SessionActionCommand):
    name = "resume"
    description = "恢复历史会话"
    usage = "/resume [session_id]"

    async def _action(self, session_id: str, ctx: AgentState) -> CommandResult:
        try:
            messages = self._sm.resume(session_id)
        except FileNotFoundError:
            return CommandResult(output=f"会话不存在: {session_id}")
        ctx.messages = messages
        lines = [f"恢复会话: {session_id}, {len(messages)} 条消息\n"]
        for msg in messages:
            role = "用户" if msg.role == "user" else "AI"
            content = msg.content
            lines.append(f"{role}: {content}")

        return CommandResult(output="\n".join(lines))
            


class DeleteCommand(SessionActionCommand):
    name = "delete"
    description = "删除历史会话"
    usage = "/delete [session_id]"

    async def _action(self, session_id: str, ctx: AgentState) -> CommandResult:
        if self._sm.delete_session(session_id):
            return CommandResult(output=f"已删除会话: {session_id}")
        return CommandResult(output=f"会话不存在: {session_id}")



