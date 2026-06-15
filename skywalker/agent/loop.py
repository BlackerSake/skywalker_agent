
import asyncio

from skywalker.llm.base import LLMClient
from skywalker.core import AgentState, LoopPhase, LoopState, Message, Role
from skywalker.agent.context import SimpleTokenizer
from skywalker.memory import ConversationManager, MemoryManager
from skywalker.tools.registry import ToolRegistry
from skywalker.tools.executor import ToolExecutor
from skywalker.tools.base import ToolBase, ToolResult, ToolError
__all__ = ["AgentState", "LoopPhase", "LoopState", "Message", "Role"]

SYSTEM_PROMPT = "你是一个有用的助手。简洁回答问题。"


async def run_loop(state: AgentState, 
                   llm: LLMClient, 
                   user_input: str,
                   conv_manager: ConversationManager | None = None,
                   memory_manager: MemoryManager | None = None,
                   system_prompt: str | None = None,
                   registry: ToolRegistry | None = None,
                   executor: ToolExecutor | None = None,
                   ) -> AgentState:
    """运行一次完整的对话循环：INIT → THINKING → TERMINATED"""

    state.messages.append(Message(Role.USER, user_input))
    state.loop_state.phase = LoopPhase.THINKING

    # 使用会话管理器的消息列表（如果提供）
    messages = conv_manager.messages if conv_manager else state.messages
    prompt = system_prompt or SYSTEM_PROMPT

    try:
        # THINKING: 调用 LLM  获取 LLM 响应
        tool_schema = registry.get_schema() if registry else None
        response = llm.chat(messages, system=prompt, tools = tool_schema)
        state.loop_state.phase = LoopPhase.PARSING

        # PARSING: 检查是否有 tool 调用
        if response.tool_calls and executor and registry:
            state.loop_state.phase = LoopPhase.EXECUTING

            # EXECUTING: 执行 tool 调用
            results = await executor.run_all(response.tool_calls, registry)
            state.loop_state.phase = LoopPhase.OBSERVING

            # OBSERVING: 观察 tool 调用结果,将 结果添加到messages中
            state.messages.append(Message(Role.ASSISTANT, response.content or ""))
            for tc, result in zip(response.tool_calls, results):
                if isinstance(result, ToolResult):
                    content = result.output
                else:
                    content = f"Error: {result.error}"
                state.messages.append(Message(Role.TOOL, content, tool_call_id=tc.id))

            # 更新 会话管理器
            if conv_manager:
                for msg in state.messages[-len(response.tool_calls) - 1:]:
                    conv_manager.add_message(msg)
                if conv_manager.should_compress():
                    await conv_manager.compress()
                    state.messages = conv_manager.messages
            
            # 转到 THINKING, 继续下一轮
            state.loop_state.phase = LoopPhase.THINKING
            return state

        state.messages.append(Message(Role.ASSISTANT, response.content))

        # 会话管理器追加消息
        if conv_manager:
            conv_manager.add_message(Message(Role.ASSISTANT, response.content))
            # 检查是否需要压缩
            if conv_manager.should_compress():
                await conv_manager.compress()
                state.messages = conv_manager.messages

        state.current_response = response.content
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


