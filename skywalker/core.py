from enum import Enum
from dataclasses import dataclass, field


class Role(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


def _make_hashable(obj):
    """递归将 dict/list 转为可 hash 的 tuple。"""
    if isinstance(obj, dict):
        return tuple(sorted((k, _make_hashable(v)) for k, v in obj.items()))
    if isinstance(obj, (list, tuple)):
        return tuple(_make_hashable(item) for item in obj)
    return obj


@dataclass(frozen=True)
class Message:
    role: Role
    content: str | list[dict]
    tool_call_id: str | None = None

    def __hash__(self):
        return hash((self.role, _make_hashable(self.content), self.tool_call_id))

    @property
    def text_content(self) -> str:
        """返回纯文本内容。str 直接返回，list 则拼接 text block。"""
        if isinstance(self.content, str):
            return self.content
        return " ".join(
            b.get("text", "") for b in self.content if b.get("type") == "text"
        )


class LoopPhase(Enum):
    INIT = "init"
    THINKING = "thinking"
    PARSING = "parsing"
    EXECUTING = "executing"
    OBSERVING = "observing"
    COMPRESSING = "compressing"
    TERMINATED = "terminated"



@dataclass
class LoopState:
    phase: LoopPhase
    error: str | None = None


@dataclass
class AgentState:
    messages: list[Message] = field(default_factory=list)
    loop_state: LoopState = field(default_factory=lambda: LoopState(LoopPhase.INIT))
    current_response: str | None = None
    project_root: str | None = None