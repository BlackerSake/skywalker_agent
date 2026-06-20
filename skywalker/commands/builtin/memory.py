from __future__ import annotations

from skywalker.ui.list_browser import ListBrowser, ListItem

from skywalker.commands.base import CommandBase, CommandResult
from skywalker.core import AgentState
from skywalker.memory.long_term import MemoryManager


class MemoryCommand(CommandBase):
    """管理记忆（list/search/clear）"""

    name = "memory"
    description = "管理记忆（list/search/clear）"
    usage = "/memory <list|search|clear> [query]"

    def __init__(self, memory_manager: MemoryManager, console):
        self._mm = memory_manager
        self._console = console

    async def execute(self, args: list[str], ctx: AgentState) -> CommandResult:
        if not args:
            return CommandResult(
                output="用法: /memory <list|search|clear> [query]"
            )

        sub = args[0]
        if sub == "list":
            return self._list()
        elif sub == "search":
            return self._search(" ".join(args[1:]))
        elif sub == "clear":
            return self._clear()
        else:
            return CommandResult(
                output=f"未知子命令: {sub}，可用: list, search, clear"
            )

    def _list(self) -> CommandResult:
        """列出所有记忆条目"""
        project_entries = self._mm._project_memory.load()
        user_entries = self._mm._user_memory.load()
        
        items = []
        # 添加项目记忆
        for e in project_entries:
            items.append(ListItem(
                id = e.id,
                title = f"[{e.type.value}] {e.content[:60]}",
                subtitle = f"重要性: {e.importance}",
                detail = e.content
            ))
        # 添加用户记忆
        for e in user_entries:
            items.append(ListItem(
                id = e.id,
                title = f"[{e.type.value}] {e.content[:60]}",
                subtitle = f"重要性: {e.importance}",
                detail = e.content
            ))

        if not items:
            return CommandResult(output="没有记忆")
        browser = ListBrowser(console=self._console)
        browser.run(items, title=f"项目记忆(项目: {len(project_entries)},用户: {len(user_entries)})")
        return CommandResult(output="")
    def _search(self, query: str) -> CommandResult:
        """关键词搜索记忆"""
        if not query:
            return CommandResult(output="用法: /memory search <关键词>")

        results = self._mm._project_memory.search(query, top_k=5)
        if not results:
            return CommandResult(output=f"未找到与 '{query}' 相关的记忆")

        items = [
            ListItem(
                id = e.id,
                title = f"[{e.type.value}] {e.content[:60]}",
                subtitle = f"重要性: {e.importance}",
                detail = e.content
            ) for e in results
        ]
        browser = ListBrowser(console=self._console)
        browser.run(items, title=f"搜索结果{query}")
        return CommandResult(output="")

    def _clear(self) -> CommandResult:
        """清空项目记忆"""
        self._mm._project_memory.save([])
        return CommandResult(output="项目记忆已清空")