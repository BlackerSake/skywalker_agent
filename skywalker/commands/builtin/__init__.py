

from skywalker.commands.builtin.memory import MemoryCommand
from skywalker.commands.builtin.session import (
    DeleteCommand,
    ListCommand,
    RenameCommand,
    ResumeCommand,
    SaveCommand,
)
from skywalker.commands.builtin.system import (
    HelpCommand, StatusCommand, ExitCommand
)
from skywalker.commands.registry import CommandRegistry
from skywalker.memory.long_term import MemoryManager
from skywalker.session.manager import SessionManager



def register_builtin_commands(registry, session_manager=None, memory_manager=None):
    # 系统命令
    registry.register(HelpCommand(registry))
    registry.register(ExitCommand())
    registry.register(StatusCommand(session_manager))

    # 会话命令
    if session_manager:
        registry.register(SaveCommand(session_manager))
        registry.register(ListCommand(session_manager))
        registry.register(ResumeCommand(session_manager))
        registry.register(DeleteCommand(session_manager))
        registry.register(RenameCommand(session_manager))

    # 记忆命令
    if memory_manager:
        registry.register(MemoryCommand(memory_manager))