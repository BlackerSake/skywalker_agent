

from skywalker.core import Message


class SimpleTokenizer:
    """粗略的token计数器"""
    RATIOS = {
        "zh": 2.0,  # 中文
        "en": 4.0,  # 英文
        "mix": 3.5, # 混合文本
    }
    # 元数据开销（tokens）
    OVERHEAD_PER_MESSAGE = 4 # 每条消息的 role + 分隔符等
    SYSTEM_OVERHEAD = 10 # 系统提示的额外开销

    _cache = {}

    @staticmethod
    def estimate_message_tokens(message: Message) -> int:
        """估算单条消息的 token 数"""
        # 你的实现：len(content) / CHARS_PER_TOKEN + 元数据开销
        cache_key = id(message)
        if cache_key in SimpleTokenizer._cache:
            return SimpleTokenizer._cache[cache_key]
        chars = len(message.content)

        chinese_ratio = sum(1 for c in message.content if '\u4e00' <= c <= '\u9fff') / max(chars, 1)
        if chinese_ratio > 0.75:
            result = int(chars / SimpleTokenizer.RATIOS["zh"]) # 中文文本 /2
            SimpleTokenizer._cache[cache_key] = result
            return result
        elif chinese_ratio > 0.25:
            result = int(chars / SimpleTokenizer.RATIOS["mix"]) # 混合文本 /3.5
            SimpleTokenizer._cache[cache_key] = result
            return result
        else:
            result = int(chars / SimpleTokenizer.RATIOS["en"]) # 英文文本 /4
            SimpleTokenizer._cache[cache_key] = result
            return result


    @staticmethod
    def estimate_total_tokens(messages: list[Message]) -> int:
        """估算所有消息的总 token 数"""
        if not messages:
            return 0
        total = 0
        for msg in messages:
            total += SimpleTokenizer.estimate_message_tokens(msg)
            total += SimpleTokenizer.OVERHEAD_PER_MESSAGE # 每条消息的元数据开销
        
        total += SimpleTokenizer.SYSTEM_OVERHEAD # 系统提示开销
        return total


    @staticmethod
    def truncate_messages(messages: list[Message], max_tokens: int) -> list[Message]:
        """截断消息列表到指定 token 数

        保留策略：
        - 从最老的消息开始删除
        - 保持消息顺序
        - 确保至少保留一条消息
        """
        if not messages:
            return []
        # 先估算总 token 数，如果已经在限制内，直接返回
        msg_tokens = [SimpleTokenizer.estimate_message_tokens(msg)
                      for msg in messages]
        
        total_tokens = (sum(msg_tokens) + 
                        SimpleTokenizer.OVERHEAD_PER_MESSAGE * len(messages) + 
                        SimpleTokenizer.SYSTEM_OVERHEAD)

        if total_tokens <= max_tokens:
            return messages.copy()
        
        # 从最老的消息开始删除，直到总 token 数符合要求
        for i in range(len(messages)):
            total_tokens -= (msg_tokens[i] + SimpleTokenizer.OVERHEAD_PER_MESSAGE)
            if total_tokens <= max_tokens:
                return messages[i+1:].copy()
        return [messages[-1]]

    @staticmethod
    def clear_cache():
        """清除 token 估算缓存"""
        SimpleTokenizer._cache.clear()