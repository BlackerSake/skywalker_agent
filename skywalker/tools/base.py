from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class ToolResult:
    """"""
    tool_call_id: str
    output: str
    truncated: bool = False

@dataclass
class ToolError:
    tool_call_id: str
    error: str
    reason: Literal["denied", "timeout", "user_rejected", "execution_error"]

class ToolBase(ABC):
    name: str
    description: str
    parameters: dict  # JSON Schema

    @abstractmethod
    async def execute(self, arguments: dict) -> ToolResult | ToolError: 
        ...

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

