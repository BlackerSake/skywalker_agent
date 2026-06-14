from abc import ABC, abstractmethod
from ast import arguments
from dataclasses import dataclass
from os import name
from dataclasses import field
from yaml import Token
from skywalker.core import Message


class LLMClient(ABC):
    @abstractmethod
    def chat(self, messages: list[Message], system: str | None = None) -> str:
        """发送消息，返回响应内容"""
        pass

@dataclass
class ToolCall:
    """工具调用"""
    id: str
    name: str
    arguments: dict

@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Token | None = None