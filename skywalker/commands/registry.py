
from __future__ import annotations

from skywalker.commands.base import CommandBase, CommandResult
from skywalker.core import AgentState


class CommandRegistry:
    """维护命令注册表, 用 /  命令名 映射 CommandBase"""
    def __init__(self):
        self._commands: dict[str, CommandBase] = {}

    def register(self, command: CommandBase) -> None:
        """注册命令"""
        self._commands[command.name] = command

    def get(self, name: str) -> CommandBase | None:
        """获取命令"""
        return self._commands.get(name)

    async def dispatch(self, raw_input: str, ctx: AgentState) -> CommandResult :
        """解析并执行命令 格式: /name [args]"""
        parts = raw_input.strip().split()
        name = parts[0][1:]  # 去掉 /
        args = parts[1:]

        command = self._commands.get(name)
        if not command:
            return CommandResult(f"Unknown command: {name},input /help for help")
        return await command.execute(args, ctx)
    
    def help_text(self) -> str:
        """获取帮助信息"""
        lines = [f"Available commands:"]
        for command in self._commands.values():
            lines.append(f"  {command.usage:<24} {command.description}")
        return "\n".join(lines)

