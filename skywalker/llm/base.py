from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator

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


@dataclass
class StreamChunk:
    """流式输出的单个 chunk"""
    type: str  # "text_delta" | "tool_use_start" | "tool_use_delta" | "message_stop"
    text: str = ""
    tool_call: ToolCall | None = None


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

    async def chat_stream(
        self,
        messages: list[Message],
        system: str | None = None,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """流式发送消息，yield StreamChunk。默认实现调用 chat() 一次性返回。"""
        response = self.chat(messages, system=system, tools=tools)
        if response.content:
            yield StreamChunk(type="text_delta", text=response.content)
        for tc in response.tool_calls:
            yield StreamChunk(type="tool_use_start", tool_call=tc)
        yield StreamChunk(type="message_stop")
