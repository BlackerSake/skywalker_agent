from abc import ABC, abstractmethod
from skywalker.core import Message


class LLMClient(ABC):
    @abstractmethod
    def chat(self, messages: list[Message], system: str | None = None) -> str:
        """发送消息，返回响应内容"""
        pass