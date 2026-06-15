from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from skywalker.core import Message


@dataclass
class ToolCall:
    """LLM 返回的单个工具调用"""
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """LLM 返回的结构化响应"""
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMClient(ABC):
    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        system: str | None = None,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """发送消息，返回 LLMResponse（含 content 和 tool_calls）"""
        pass
