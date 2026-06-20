
from __future__ import annotations
from abc import ABC, abstractmethod


from skywalker.core import Message, Role
from skywalker.memory.base import MemoryEntry

"""短期记忆 - 会话级管理与压缩

职责： 管理单次会话的消息队列，增量追踪 token 使用量，在超限时触发压缩。
压缩器将旧消息摘要为一条 system 消息，释放 token 空间。


"""

class CompressorBase(ABC):
    """压缩器基类"""

    @abstractmethod
    async def compress(self, messages: list[Message]) -> str:
        """将消息列表压缩为摘要文本"""
        pass

class LLMCompressor(CompressorBase):
    """LLM 压缩器"""
    def __init__(self, llm):
        self.llm = llm

    async def compress(self, messages: list[Message]) -> str:
        """调用LLM将消息压缩为摘要"""
        context_parts = []
        for msg in messages:
            role_name = msg.role.value.upper()
            context_parts.append(f"{role_name}: {msg.text_content}")
        context_text = "\n".join(context_parts)

        summary_prompt = (
            "请将以下对话历史压缩为简洁的摘要，保留关键事实、决策和待办事项，"
            "丢弃冗余的寒暄和重复内容。摘要应控制在 200 字以内。\n\n"
            f"对话历史：\n{context_text}"
        )

        summary_msg = Message(Role.USER, summary_prompt)
        return self.llm.chat([summary_msg]).content

class SubAgentCompressor(CompressorBase):
    """子代理压缩器"""
    async def compress(self, messages: list[Message]) -> str:
        """将消息列表压缩为摘要文本"""
        raise NotImplementedError("SubAgentCompressor 将在 V5 实现")



class ConversationManager:
    def __init__(
        self,
        compressor: CompressorBase,
        max_tokens: int,
        compress_threshold: float = 0.75,
    ):
        self._compressor = compressor
        self._max_tokens = max_tokens
        self._compress_threshold = compress_threshold
        self._messages: list[Message] = []
        self._total_tokens = 0

    def add_message(self, message: Message) -> None:
        """追加消息,并增加token使用计数"""
        from skywalker.agent.context import SimpleTokenizer
        self._messages.append(message)
        self._total_tokens += SimpleTokenizer.estimate_message_tokens(message)
        self._total_tokens += SimpleTokenizer.OVERHEAD_PER_MESSAGE

    def should_compress(self) -> bool:
        """检查 是否需要压缩"""
        if self._max_tokens <= 0:
            return False
        usage = self._total_tokens / self._max_tokens
        return usage >= self._compress_threshold
    async def compress(self) -> None:
        """执行压缩,压缩为一条systeam消息"""
        if not self._messages:
            return
        # 分离system 与 非 system
        system_messages = [msg for msg in self._messages if msg.role == Role.SYSTEM]
        non_system_messages = [msg for msg in self._messages if msg.role != Role.SYSTEM]
        if not non_system_messages:
            return
        
        # 压缩前半部分非system消息
        split_point = len(non_system_messages) // 2
        to_compress = non_system_messages[:split_point]
        to_keep = non_system_messages[split_point:]

        if not to_compress:
            return
        
        # 调用压缩器进行压缩
        summary_text = await self._compressor.compress(to_compress)

        # 构造摘要消息
        summary_msg = Message(Role.SYSTEM, f"[SUMMARY]{summary_text}")

        # 将压缩后的消息插入到非system消息列表中
        self._messages = system_messages + [summary_msg] + to_keep

        # 重新计算token使用计数
        from skywalker.agent.context import SimpleTokenizer
        self._total_tokens = SimpleTokenizer.estimate_total_tokens(self._messages)

    @property
    def messages(self) -> list[Message]:
        """获取并返回消息列表  的只读版本"""
        return list(self._messages)
    @property
    def total_tokens(self) -> int:
        """获取并返回总token使用计数"""
        return self._total_tokens

    def clear(self) -> None:
        """清空消息列表和 token 计数"""
        self._messages.clear()
        self._total_tokens = 0

