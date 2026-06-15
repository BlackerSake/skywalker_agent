from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from skywalker.core import AgentState

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