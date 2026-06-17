from __future__ import annotations

from skywalker.commands.base import CommandBase, CommandResult
from skywalker.core import AgentState
from skywalker.memory.long_term import MemoryManager


class MemoryCommand(CommandBase):
    """管理记忆（list/search/clear）"""

    name = "memory"
    description = "管理记忆（list/search/clear）"
    usage = "/memory <list|search|clear> [query]"

    def __init__(self, memory_manager: MemoryManager):
        self._mm = memory_manager

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

        lines = [f"项目记忆 ({len(project_entries)} 条):"]
        for e in project_entries[:10]:
            lines.append(f"  [{e.type.value}] {e.content[:60]}")

        lines.append(f"\n用户记忆 ({len(user_entries)} 条):")
        for e in user_entries[:10]:
            lines.append(f"  [{e.type.value}] {e.content[:60]}")

        return CommandResult(output="\n".join(lines))

    def _search(self, query: str) -> CommandResult:
        """关键词搜索记忆"""
        if not query:
            return CommandResult(output="用法: /memory search <关键词>")

        results = self._mm._project_memory.search(query, top_k=5)
        if not results:
            return CommandResult(output=f"未找到与 '{query}' 相关的记忆")

        lines = [f"搜索结果（{len(results)} 条）:"]
        for e in results:
            lines.append(f"  [{e.type.value}] {e.content[:80]}")
        return CommandResult(output="\n".join(lines))

    def _clear(self) -> CommandResult:
        """清空项目记忆"""
        self._mm._project_memory.save([])
        return CommandResult(output="项目记忆已清空")