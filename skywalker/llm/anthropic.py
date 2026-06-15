from __future__ import annotations

import os

from dotenv import load_dotenv
from anthropic import Anthropic

from skywalker.core import Message, Role
from skywalker.llm.base import LLMClient, LLMResponse, ToolCall


load_dotenv(override=True)

MODEL = os.environ["MODEL_ID"]
BASE_URL = os.environ.get("ANTHROPIC_BASE_URL")
API_KEY = os.environ["ANTHROPIC_API_KEY"]


class AnthropicClient(LLMClient):
    def __init__(self):
        self.client = Anthropic(base_url=BASE_URL, api_key=API_KEY)
        self.model = MODEL

    def chat(self,
             messages: list[Message],
             system: str | None = None,
             tools: list[dict] | None = None) -> LLMResponse:
        formatted = [
            {"role": m.role.value, "content": m.content}
            for m in messages
        ]

        kwargs = {
            "model": self.model,
            "messages": formatted,
            "max_tokens": 4096,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        response = self.client.messages.create(**kwargs)
        
        content =""
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use": #Anthropic 的响应内容块是 tool_use
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input,
                    )
                )
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
        )


