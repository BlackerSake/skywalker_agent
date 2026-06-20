
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Callable

from skywalker.llm.base import LLMClient, StreamChunk
from skywalker.core import AgentState, LoopPhase, LoopState, Message, Role
from skywalker.agent.context import SimpleTokenizer
from skywalker.memory import ConversationManager, MemoryManager
from skywalker.tools.registry import ToolRegistry
from skywalker.tools.executor import ToolExecutor
from skywalker.tools.base import ToolBase, ToolResult, ToolError
from skywalker.ui.output import (
    StreamEvent, AgentTextStreaming, AgentTurnComplete,
    ToolExecutionStarted, ToolExecutionCompleted, CompactProgressEvent,
)

__all__ = ["AgentState", "LoopPhase", "LoopState", "Message", "Role"]

logger = logging.getLogger("skywalker.agent")

SYSTEM_PROMPT = "你是一个有用的助手。简洁回答问题。"

# 事件回调类型
EventCallback = Callable[[StreamEvent], None]


async def run_loop(state: AgentState,
                   llm: LLMClient,
                   user_input: str,
                   conv_manager: ConversationManager | None = None,
                   memory_manager: MemoryManager | None = None,
                   system_prompt: str | None = None,
                   registry: ToolRegistry | None = None,
                   executor: ToolExecutor | None = None,
                   on_event: EventCallback | None = None,
                   tool_log=None,  # ToolLog 实例，可选
                   turn_index: int = 0,
                   ) -> AgentState:
    """运行完整的对话循环，支持多轮 Think→Act→Observe"""

    state.messages.append(Message(Role.USER, user_input))
    prompt = system_prompt or SYSTEM_PROMPT
    logger.debug(f"▶ 开始对话循环 | user_input={user_input[:100]}")

    try:
        while True:
            state.loop_state.phase = LoopPhase.THINKING
            logger.info(f"⏳ Phase: THINKING")
            messages = conv_manager.messages if conv_manager else state.messages
            tool_schema = registry.get_schema() if registry else None

            # 流式调用 LLM
            full_text = ""
            tool_calls = []
            async for chunk in llm.chat_stream(messages, system=prompt, tools=tool_schema):
                if chunk.type == "text_delta":
                    full_text += chunk.text
                    if on_event:
                        on_event(AgentTextStreaming(text=chunk.text))
                elif chunk.type == "tool_use_start" and chunk.tool_call:
                    tool_calls.append(chunk.tool_call)
                elif chunk.type == "message_stop":
                    pass

            state.loop_state.phase = LoopPhase.PARSING
            logger.info(f"🔍 Phase: PARSING | text_len={len(full_text)}, tool_calls={len(tool_calls)}")

            # 无工具调用 → 正常结束
            if not tool_calls or not executor or not registry:
                state.messages.append(Message(Role.ASSISTANT, full_text))
                if conv_manager:
                    conv_manager.add_message(Message(Role.ASSISTANT, full_text))
                    if conv_manager.should_compress():
                        if on_event:
                            on_event(CompactProgressEvent(message="Compressing..."))
                        await conv_manager.compress()
                        state.messages = conv_manager.messages
                state.current_response = full_text
                state.loop_state.phase = LoopPhase.TERMINATED
                logger.info(f"✅ Phase: TERMINATED | response_len={len(full_text)}")
                if on_event:
                    on_event(AgentTurnComplete(full_text=full_text))
                return state

            # 有工具调用 → 执行
            state.loop_state.phase = LoopPhase.EXECUTING
            logger.info(f"⚙️ Phase: EXECUTING | tools={[tc.name for tc in tool_calls]}")

            # 记录开始时间
            tool_start_times = {}

            for tc in tool_calls:
                logger.debug(f"  ⏵ {tc.name} | input={tc.arguments}")
                tool_start_times[tc.id] = time.monotonic()
                if on_event:
                    on_event(ToolExecutionStarted(tool_name=tc.name, tool_input=tc.arguments))

            results = await executor.run_all(tool_calls, registry)
            state.loop_state.phase = LoopPhase.OBSERVING
            logger.info(f"👁️ Phase: OBSERVING | results_count={len(results)}")

            for tc, result in zip(tool_calls, results):
                output = result.output if isinstance(result, ToolResult) else f"Error: {result.error}"
                exit_code = 0 if isinstance(result, ToolResult) else 1

                if on_event:
                    on_event(ToolExecutionCompleted(
                        tool_name=tc.name,
                        output=output,
                        exit_code=exit_code,
                    ))

                # 写入 tool_log
                if tool_log:
                    duration_ms = int((time.monotonic() - tool_start_times.get(tc.id, 0)) * 1000)
                    from skywalker.session.tool_log import ToolCallRecord
                    tool_log.append(ToolCallRecord(
                        turn_index=turn_index,
                        tool_name=tc.name,
                        tool_input=tc.arguments,
                        output=output,
                        exit_code=exit_code,
                        started_at=datetime.now(timezone.utc).isoformat(),
                        duration_ms=duration_ms,
                    ))

            # 构造 assistant 消息（text + tool_use blocks）
            assistant_content = []
            if full_text:
                assistant_content.append({"type": "text", "text": full_text})
            for tc in tool_calls:
                assistant_content.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.arguments,
                })
            state.messages.append(Message(Role.ASSISTANT, assistant_content))

            # 构造 tool_result 消息（合并为一条 user 消息）
            tool_results = []
            for tc, result in zip(tool_calls, results):
                output = result.output if isinstance(result, ToolResult) else f"Error: {result.error}"
                tool_results.append({"type": "tool_result", "tool_use_id": tc.id, "content": output})
            state.messages.append(Message(Role.USER, tool_results))

            # 更新会话管理器
            if conv_manager:
                for msg in state.messages[-2:]:
                    conv_manager.add_message(msg)
                if conv_manager.should_compress():
                    logger.info("🗜️ 触发压缩")
                    if on_event:
                        on_event(CompactProgressEvent(message="Compressing..."))
                    await conv_manager.compress()
                    state.messages = conv_manager.messages

            # 继续循环，再次调用 LLM 获取最终回复

    except Exception as e:
        logger.error(f"❌ 对话循环异常: {e}", exc_info=True)
        state.loop_state.error = str(e)
        state.loop_state.phase = LoopPhase.TERMINATED

    return state


async def run_loop_with_shutdown(
    state: AgentState,
    llm: LLMClient,
    user_input: str,
    conv_manager: ConversationManager,
    memory_manager: MemoryManager,
    system_prompt: str,
) -> AgentState:
    """带 shutdown 钩子的对话循环"""
    state = await run_loop(
        state, llm, user_input,
        conv_manager=conv_manager,
        memory_manager=memory_manager,
        system_prompt=system_prompt,
    )
    return state

async def shutdown(memory_manager: MemoryManager, state: AgentState) -> None:
    """对话结束时的清理钩子，写回记忆"""
    await memory_manager.on_shutdown(state)


