from __future__ import annotations

from skywalker.commands.base import CommandBase, CommandResult, SessionActionCommand
from skywalker.core import AgentState
from skywalker.session.manager import SessionManager
from skywalker.ui.render import render_messages
from skywalker.ui.list_browser import ListBrowser, ListItem

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
    def __init__(self, session_manager: SessionManager,console):
        self.session_manager = session_manager
        self._console = console

    async def execute(self, args: list[dict], ctx: AgentState) -> CommandResult:
        """列出所有会话"""
        sessions = self.session_manager.list_sessions()
        if not sessions:
            return CommandResult(output="没有历史会话")
        items = [ListItem(
            id = s.session_id,
            title = s.title,
            subtitle = f"{s.message_count} 条消息 {s.updated_at[:16] }",
            detail= f"ID: {s.session_id}\n项目:{s.project_root}"
        )for s in sessions]
        # 打开浏览器(只读)
        browser = ListBrowser(console=self._console)
        browser.run(items,title="会话列表")
        return CommandResult(output="")
    

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

    def __init__(self, session_manager: SessionManager, console):
        super().__init__(session_manager)
        self._console = console

    async def _action(self, session_id: str, ctx: AgentState) -> CommandResult:
        try:
            messages = self._sm.resume(session_id)
            return CommandResult(
                output=f"已恢复会话: {session_id},共 {len(messages)} 条消息",
                resumed_messages=messages
                )
        except FileNotFoundError:
            return CommandResult(output=f"会话不存在: {session_id}")

    async def execute(self, args: list[str], ctx: AgentState) -> CommandResult:
        # 恢复指定会话,若有参数
        if args:
            return await self._action(args[0], ctx)
        # 否则列出所有会话
        sessions = self._sm.list_sessions()
        if not sessions:
            return CommandResult(output="没有历史会话")
        items = [ListItem(
            id = s.session_id,
            title = s.title,
            subtitle = f"{s.message_count} 条消息 {s.updated_at[:16] }"
            )for s in sessions]
        browser = ListBrowser(console=self._console)
        selected = browser.run(items,title="选择会话恢复")
        if selected:
            return await self._action(selected.id, ctx)
        return CommandResult(output="取消")           


class DeleteCommand(SessionActionCommand):
    name = "delete"
    description = "删除历史会话"
    usage = "/delete [session_id]"

    def __init__(self, session_manager: SessionManager, console):
        super().__init__(session_manager)
        self._console = console

    async def _action(self, session_id: str, ctx: AgentState) -> CommandResult:
        if self._sm.delete_session(session_id):
            return CommandResult(output=f"已删除会话: {session_id}")
        return CommandResult(output=f"会话不存在: {session_id}")
    
    async def execute(self, args: list[str], ctx: AgentState) -> CommandResult:
        # 删除指定会话,若有参数
        if args:
            return await self._action(args[0], ctx)
        # 否则列出所有会话
        sessions = self._sm.list_sessions()
        if not sessions:
            return CommandResult(output="没有历史会话")
        items = [ListItem(
            id = s.session_id,
            title = s.title,
            subtitle = f"{s.message_count} 条消息 {s.updated_at[:16] }"
            )for s in sessions]
        browser = ListBrowser(console=self._console)
        selected = browser.run(items,title="选择会话删除")
        if selected:
            return await self._action(selected.id, ctx)
        return CommandResult(output="取消")
    



