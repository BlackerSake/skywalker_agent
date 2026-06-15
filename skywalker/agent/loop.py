
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
    """运行完整的对话循环，支持多轮 Think→Act→Observe"""

    state.messages.append(Message(Role.USER, user_input))
    prompt = system_prompt or SYSTEM_PROMPT

    try:
        while True:
            state.loop_state.phase = LoopPhase.THINKING
            messages = conv_manager.messages if conv_manager else state.messages
            tool_schema = registry.get_schema() if registry else None
            response = llm.chat(messages, system=prompt, tools=tool_schema)
            state.loop_state.phase = LoopPhase.PARSING

            # 无工具调用 → 正常结束
            if not response.tool_calls or not executor or not registry:
                state.messages.append(Message(Role.ASSISTANT, response.content))
                if conv_manager:
                    conv_manager.add_message(Message(Role.ASSISTANT, response.content))
                    if conv_manager.should_compress():
                        await conv_manager.compress()
                        state.messages = conv_manager.messages
                state.current_response = response.content
                state.loop_state.phase = LoopPhase.TERMINATED
                return state

            # 有工具调用 → 执行
            state.loop_state.phase = LoopPhase.EXECUTING
            results = await executor.run_all(response.tool_calls, registry)
            state.loop_state.phase = LoopPhase.OBSERVING

            # 构造 assistant 消息（text + tool_use blocks）
            assistant_content = []
            if response.content:
                assistant_content.append({"type": "text", "text": response.content})
            for tc in response.tool_calls:
                assistant_content.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.arguments,
                })
            state.messages.append(Message(Role.ASSISTANT, assistant_content))

            # 构造 tool_result 消息（合并为一条 user 消息）
            tool_results = []
            for tc, result in zip(response.tool_calls, results):
                output = result.output if isinstance(result, ToolResult) else f"Error: {result.error}"
                tool_results.append({"type": "tool_result", "tool_use_id": tc.id, "content": output})
            state.messages.append(Message(Role.USER, tool_results))

            # 更新会话管理器
            if conv_manager:
                for msg in state.messages[-2:]:
                    conv_manager.add_message(msg)
                if conv_manager.should_compress():
                    await conv_manager.compress()
                    state.messages = conv_manager.messages

            # 继续循环，再次调用 LLM 获取最终回复

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


