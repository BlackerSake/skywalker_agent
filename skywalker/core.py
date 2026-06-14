from enum import Enum
from dataclasses import dataclass, field


class Role(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass(frozen=True)
class Message:
    role: Role
    content: str


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