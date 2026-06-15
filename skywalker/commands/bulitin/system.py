

from __future__ import annotations

from skywalker.commands.base import CommandBase, CommandResult
from skywalker.commands.registry import CommandRegistry
from skywalker.core import AgentState
from skywalker.session.manager import SessionManager
from skywalker.agent.context import SimpleTokenizer

class HelpCommand(CommandBase):
    """输入 help 显示所有命令 """
    name = "help"
    description = "显示所有命令"
    usage = "/help"
    
    def __init__(self, registry: CommandRegistry):
        self.registry = registry
    async def execute(self, arguments: list[dict], ctx: AgentState) -> CommandResult:
        return CommandResult(output=self.registry.help_text())


class Exitcommand(CommandBase):
    """输入 exit 退出程序 """
    name = "exit"
    description = "退出程序"
    usage = "/exit"
    
    async def execute(self, arguments: list[dict], ctx: AgentState) -> CommandResult:
        return CommandResult(output="Sayounara!", stop=True)

class StatusCommand(CommandBase):
    """输入 status 显示当前会话状态 """
    name = "status"
    description = "显示当前会话状态"
    usage = "/status"
    
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
    async def execute(self, arguments: list[dict], ctx: AgentState) -> CommandResult:
        lines = [
            f"项目目录: {ctx.project_root}",
            f"消息数量: {len(ctx.messages)}"
        ]
        if self._session_manager:
            sid = self.session_manager.current_session_id()
            lines.append(f"当前会话: {sid or '无'}")
        
        total_tokens = SimpleTokenizer.estimate_total_tokens(ctx.messages)
        lines.append(f"Token 用量: ~{total_tokens}")

        return CommandResult(output="\n".join(lines))


