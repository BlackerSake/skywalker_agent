

from skywalker.core import Message, Role
import weakref

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

    _cache = weakref.WeakKeyDictionary()

    @staticmethod
    def estimate_message_tokens(message: Message) -> int:
        """估算单条消息的 token 数"""

        if message in SimpleTokenizer._cache:
            return SimpleTokenizer._cache[message]
        
        chars = len(message.text_content)
        chinese_ratio = sum(1 for c in message.text_content if '\u4e00' <= c <= '\u9fff') / max(chars, 1)
        
        if chinese_ratio > 0.75:
            result = int(chars / SimpleTokenizer.RATIOS["zh"]) # 中文文本 /2
        elif chinese_ratio > 0.25:
            result = int(chars / SimpleTokenizer.RATIOS["mix"]) # 混合文本 /3.5
        else:
            result = int(chars / SimpleTokenizer.RATIOS["en"]) # 英文文本 /4
        SimpleTokenizer._cache[message] = result
        return result


    @staticmethod
    def estimate_total_tokens(messages: list[Message]) -> int:
        """估算所有消息的总 token 数"""
        if not messages:
            return SimpleTokenizer.SYSTEM_OVERHEAD
        total = SimpleTokenizer.SYSTEM_OVERHEAD
        for msg in messages:
            total += SimpleTokenizer.estimate_message_tokens(msg)
            total += SimpleTokenizer.OVERHEAD_PER_MESSAGE
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
        
        #分离系统消息和用户消息
        system_msgs = []
        user_msgs = []
        for msg in messages:
            # 支持字符串和枚举两种类型
            role_value = msg.role.value if hasattr(msg.role, 'value') else msg.role
            if role_value == "system":
                system_msgs.append(msg)
            else:
                user_msgs.append(msg)
        

        system_tokens = 0
        for msg in system_msgs:
            system_tokens += SimpleTokenizer.estimate_message_tokens(msg) 
            system_tokens += SimpleTokenizer.OVERHEAD_PER_MESSAGE
        
        available_tokens = max_tokens - system_tokens - SimpleTokenizer.SYSTEM_OVERHEAD

        #系统消息已经超限,至少保留一条用户消息
        if available_tokens <= 0:
            if user_msgs: 
                return system_msgs + [user_msgs[-1]]
            return system_msgs
        
        # 获取user消息的 token 数
        user_tokens = [SimpleTokenizer.estimate_message_tokens(msg)
                      for msg in user_msgs]
        
        total_tokens = (sum(user_tokens) + system_tokens +
                        SimpleTokenizer.SYSTEM_OVERHEAD)

        if total_tokens <= max_tokens:
            return system_msgs + user_msgs.copy()
        
        # 从最老的消息开始删除
        remaining_tokens = total_tokens
        for i in range(len(user_msgs)):

            remaining_tokens -= (user_tokens[i] + SimpleTokenizer.OVERHEAD_PER_MESSAGE)

            if remaining_tokens <= available_tokens:
                return system_msgs + user_msgs[i+1:].copy()

        return system_msgs + [user_msgs[-1]] if user_msgs else system_msgs

    @staticmethod
    def clear_cache():
        """清除 token 估算缓存"""
        SimpleTokenizer._cache.clear()

    def should_compress(self, messages: list[Message]) -> bool:
        """是否需要压缩"""
        return False


"""Minds
用有状态的管理器来维护消息队列和累计 token，避免每次全量重算
## 现有问题
- 现有 `SimpleTokenizer` 是无状态的工具类，每次调用都全量计算所有消息的 token 总数。
- 随着对话历史增长，全量计算的复杂度 O(n) 会逐渐增加，且无法复用之前的结果。

context.py          → SimpleTokenizer，无状态工具，截断算法
                      V1 职责：算 token、截断，仅此而已

short_term.py       → ConversationManager，有状态队列
                      V2 职责：增量 token 管理 + 压缩摘要 + 写回触发
"""