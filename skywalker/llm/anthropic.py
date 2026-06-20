from __future__ import annotations

import json
import logging
import os
import time
from typing import AsyncIterator

from dotenv import load_dotenv
from anthropic import Anthropic

from skywalker.core import Message, Role
from skywalker.llm.base import LLMClient, LLMResponse, StreamChunk, ToolCall

load_dotenv(override=True)

logger = logging.getLogger("skywalker.llm")

MODEL = os.environ["MODEL_ID"]
BASE_URL = os.environ.get("ANTHROPIC_BASE_URL")
API_KEY = os.environ["ANTHROPIC_API_KEY"]


class AnthropicClient(LLMClient):
    def __init__(self):
        self.client = Anthropic(base_url=BASE_URL, api_key=API_KEY)
        self.model = MODEL
        logger.info(f"🤖 初始化 LLM | model={MODEL}")

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

        logger.debug(f"📤 LLM 请求 | messages={len(formatted)}, tools={len(tools) if tools else 0}")
        start_time = time.monotonic()

        response = self.client.messages.create(**kwargs)

        elapsed = time.monotonic() - start_time
        content = ""
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input,
                    )
                )

        logger.info(f"📥 LLM 响应 | 耗时={elapsed:.2f}s | text_len={len(content)} | tool_calls={len(tool_calls)}")
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
        )

    async def chat_stream(
        self,
        messages: list[Message],
        system: str | None = None,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """流式发送消息"""
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

        logger.debug(f"📤 LLM 流式请求 | messages={len(formatted)}, tools={len(tools) if tools else 0}")
        start_time = time.monotonic()

        # 当前正在构建的 tool_use 信息
        current_tool_id = None
        current_tool_name = None
        current_tool_input_json = ""
        text_len = 0
        tool_count = 0

        with self.client.messages.stream(**kwargs) as stream:
            for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        current_tool_id = block.id
                        current_tool_name = block.name
                        current_tool_input_json = ""

                elif event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        text_len += len(delta.text)
                        yield StreamChunk(type="text_delta", text=delta.text)
                    elif delta.type == "input_json_delta":
                        current_tool_input_json += delta.partial_json

                elif event.type == "content_block_stop":
                    if current_tool_id and current_tool_name:
                        tool_count += 1
                        try:
                            arguments = json.loads(current_tool_input_json) if current_tool_input_json else {}
                        except json.JSONDecodeError:
                            arguments = {}
                        yield StreamChunk(
                            type="tool_use_start",
                            tool_call=ToolCall(
                                id=current_tool_id,
                                name=current_tool_name,
                                arguments=arguments,
                            ),
                        )
                        current_tool_id = None
                        current_tool_name = None
                        current_tool_input_json = ""

                elif event.type == "message_stop":
                    elapsed = time.monotonic() - start_time
                    logger.info(f"📥 LLM 流式完成 | 耗时={elapsed:.2f}s | text_len={text_len} | tool_calls={tool_count}")
                    yield StreamChunk(type="message_stop")


