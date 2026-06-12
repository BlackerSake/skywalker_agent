
from skywalker.llm.base import LLMClient
from skywalker.core import AgentState, LoopPhase, LoopState, Message, Role
from skywalker.agent.context import SimpleTokenizer

__all__ = ["AgentState", "LoopPhase", "LoopState", "Message", "Role"]

SYSTEM_PROMPT = "你是一个有用的助手。简洁回答问题。"


def run_loop(state: AgentState, llm: LLMClient, user_input: str) -> AgentState:
    """运行一次完整的对话循环：INIT → THINKING → TERMINATED"""

    state.messages.append(Message(Role.USER, user_input))
    state.loop_state.phase = LoopPhase.THINKING

    try:
        response = llm.chat(state.messages, system=SYSTEM_PROMPT)
        state.messages.append(Message(Role.ASSISTANT, response))
        if SimpleTokenizer().should_compress(state.messages):
            """预留截断逻辑"""
            pass
        state.current_response = response
        state.loop_state.phase = LoopPhase.TERMINATED
    except Exception as e:
        state.loop_state.error = str(e)
        state.loop_state.phase = LoopPhase.TERMINATED

    return state