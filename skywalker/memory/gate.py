"""MemoryGate — 会话记忆写入的两层过滤器

规则层：快速过滤明显无意义的会话（零 LLM 成本）
LLM 层：语义判断是否值得保存，提取 MemoryEntry 列表
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from skywalker.core import Message, Role
from skywalker.memory.base import MemoryEntry, MemoryType

logger = logging.getLogger(__name__)


@dataclass
class GateResult:
    """Gate 评估结果"""
    passed: bool                          # 是否通过 Gate
    reason: str = ""                      # 未通过的原因
    entries: list[MemoryEntry] | None = None  # 通过时提取的条目


class MemoryGate:
    """会话记忆写入的两层过滤器"""

    # ── 规则层配置 ──
    MIN_ROUNDS = 2             # 最少对话轮次
    MIN_USER_MSG_LEN = 10      # 用户消息最短有效长度（字符）

    def __init__(self, llm=None):
        """
        Args:
            llm: LLMClient 实例，用于 LLM 层评估。为 None 时跳过 LLM 层。
        """
        self._llm = llm

    async def evaluate(self, messages: list[Message]) -> GateResult:
        """评估会话是否值得保存为记忆。

        流程：规则层 → LLM 层 → 返回结果
        """
        # ── 规则层 ──
        rule_result = self._rule_check(messages)
        if not rule_result.passed:
            logger.info(f"Gate 规则层拦截: {rule_result.reason}")
            return rule_result

        # ── LLM 层 ──
        if not self._llm:
            # 无 LLM 实例，跳过 LLM 层，直接通过
            return GateResult(passed=True, reason="no LLM, rule layer only")

        return await self._llm_evaluate(messages)

    def _rule_check(self, messages: list[Message]) -> GateResult:
        """规则层：快速过滤明显无意义的会话"""

        # 分离用户和助手消息
        user_msgs = [m for m in messages if m.role == Role.USER]
        assistant_msgs = [m for m in messages if m.role == Role.ASSISTANT]

        # 1. 对话轮次不足
        if len(user_msgs) < self.MIN_ROUNDS:
            return GateResult(passed=False, reason=f"对话轮次不足 ({len(user_msgs)} < {self.MIN_ROUNDS})")

        # 2. 检查是否有工具调用（list content 表示有 tool_use/tool_result）
        has_tool_use = any(
            isinstance(m.content, list) and
            any(b.get("type") == "tool_use" for b in m.content)
            for m in messages
        )

        # 3. 检查用户消息是否有实质内容
        substantial_user_msgs = [
            m for m in user_msgs
            if len(m.text_content.strip()) >= self.MIN_USER_MSG_LEN
        ]

        # 4. 检查是否包含代码或技术内容
        all_text = " ".join(m.text_content for m in messages)
        has_code = any(marker in all_text for marker in [
            "```", "def ", "class ", "import ", "function ", "const ", "var ",
            "Error:", "Traceback", "Exception", "error:",
        ])

        # 5. 判断是否有实质信息
        has_substance = has_tool_use or has_code or len(substantial_user_msgs) >= 2

        if not has_substance:
            return GateResult(passed=False, reason="纯闲聊，无工具调用、无代码、无实质信息")

        return GateResult(passed=True, reason="规则层通过")

    async def _llm_evaluate(self, messages: list[Message]) -> GateResult:
        """LLM 层：语义判断是否值得保存，提取 MemoryEntry"""

        # 构造评估 prompt
        context_parts = []
        for msg in messages:
            text = msg.text_content.strip()
            if text:
                context_parts.append(f"{msg.role.value.upper()}: {text}")
        conversation = "\n".join(context_parts)

        eval_prompt = Message(Role.USER, (
            "你是一个记忆管理器。分析以下对话，判断是否有值得长期保存的信息。\n\n"
            "值得保存的信息类型：\n"
            "- 用户明确表达的偏好（如姓名、习惯、风格偏好）\n"
            "- 重要的事实或决策\n"
            "- 项目相关的架构或设计决策\n"
            "- bug 修复记录或技术发现\n\n"
            "不值得保存的：\n"
            "- 简单的问候和寒暄\n"
            "- 一次性的查询结果\n"
            "- 无结论的讨论\n\n"
            "如果值得保存，输出格式（每条一行）：\n"
            "SAVE|type|importance|content\n"
            "type: fact/preference/architecture/bugfix\n"
            "importance: 0.4-1.0\n\n"
            "如果不值得保存，输出：\n"
            "SKIP\n\n"
            f"对话历史：\n{conversation}"
        ))

        try:
            response = self._llm.chat([eval_prompt])
            result_text = response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            logger.warning(f"Gate LLM 评估失败: {e}")
            return GateResult(passed=False, reason=f"LLM 评估异常: {e}")

        # 解析结果
        lines = [l.strip() for l in result_text.strip().split("\n") if l.strip()]

        if not lines or lines[0].upper() == "SKIP":
            return GateResult(passed=False, reason="LLM 判断无需保存")

        entries = []
        type_map = {
            "fact": MemoryType.FACT,
            "preference": MemoryType.PREFERENCE,
            "architecture": MemoryType.ARCHITECTURE,
            "bugfix": MemoryType.BUGFIX,
        }

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        for line in lines:
            if not line.upper().startswith("SAVE|"):
                continue
            parts = line.split("|", 3)
            if len(parts) < 4:
                continue

            _, type_str, importance_str, content = parts
            type_str = type_str.strip().lower()
            importance_str = importance_str.strip()

            try:
                importance = float(importance_str)
            except ValueError:
                continue

            # importance < 0.4 丢弃
            if importance < 0.4:
                continue

            mem_type = type_map.get(type_str, MemoryType.FACT)
            entries.append(MemoryEntry(
                id=f"gate-{now.strftime('%Y%m%d%H%M%S')}-{len(entries)}",
                type=mem_type,
                content=content.strip(),
                importance=importance,
                source="session",
                create_at=now,
                updated_at=now,
                tags=["gate-extracted"],
            ))

        if not entries:
            return GateResult(passed=False, reason="LLM 未提取到有效条目")

        return GateResult(passed=True, reason=f"LLM 提取 {len(entries)} 条", entries=entries)
