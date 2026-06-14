
import asyncio

from skywalker.llm.base import LLMClient
from skywalker.core import AgentState, LoopPhase, LoopState, Message, Role
from skywalker.agent.context import SimpleTokenizer
from skywalker.memory import ConversationManager, MemoryManager

__all__ = ["AgentState", "LoopPhase", "LoopState", "Message", "Role"]

SYSTEM_PROMPT = "你是一个有用的助手。简洁回答问题。"


async def run_loop(state: AgentState, 
                   llm: LLMClient, 
                   user_input: str,
                   conv_manager: ConversationManager | None = None,
                   memory_manager: MemoryManager | None = None,
                   system_prompt: str | None = None) -> AgentState:
    """运行一次完整的对话循环：INIT → THINKING → TERMINATED"""

    state.messages.append(Message(Role.USER, user_input))
    state.loop_state.phase = LoopPhase.THINKING

    # 使用会话管理器的消息列表（如果提供）
    messages = conv_manager.messages if conv_manager else state.messages
    prompt = system_prompt or SYSTEM_PROMPT

    try:
        response = llm.chat(messages, system=prompt)
        state.messages.append(Message(Role.ASSISTANT, response))

        # 会话管理器追加消息
        if conv_manager:
            conv_manager.add_message(Message(Role.ASSISTANT, response))
            # 检查是否需要压缩
            if conv_manager.should_compress():
                await conv_manager.compress()
                state.messages = conv_manager.messages

        state.current_response = response
        state.loop_state.phase = LoopPhase.TERMINATED
    except Exception as e:
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


