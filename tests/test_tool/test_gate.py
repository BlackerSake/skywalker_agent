"""skywalker.memory.gate 测试"""
import pytest
from unittest.mock import MagicMock

from skywalker.core import Message, Role
from skywalker.memory.base import MemoryType
from skywalker.memory.gate import MemoryGate, GateResult


# ── 规则层测试 ──────────────────────────────────────────────

class TestRuleLayer:
    def test_too_few_rounds(self):
        """对话轮次 < 2 → 拦截"""
        gate = MemoryGate()
        messages = [Message(Role.USER, "hello")]
        result = gate._rule_check(messages)
        assert result.passed is False
        assert "轮次不足" in result.reason

    def test_pure_chitchat(self):
        """纯闲聊，无工具/代码 → 拦截"""
        gate = MemoryGate()
        messages = [
            Message(Role.USER, "hi"),
            Message(Role.ASSISTANT, "hello!"),
            Message(Role.USER, "how are you"),
            Message(Role.ASSISTANT, "I'm good!"),
        ]
        result = gate._rule_check(messages)
        assert result.passed is False
        assert "纯闲聊" in result.reason

    def test_has_tool_use_passes(self):
        """有工具调用 → 通过"""
        gate = MemoryGate()
        messages = [
            Message(Role.USER, "read the file"),
            Message(Role.ASSISTANT, [
                {"type": "text", "text": "let me read it"},
                {"type": "tool_use", "id": "tc1", "name": "file", "input": {}},
            ]),
            Message(Role.USER, [
                {"type": "tool_result", "tool_use_id": "tc1", "content": "file content"},
            ]),
        ]
        result = gate._rule_check(messages)
        assert result.passed is True

    def test_has_code_passes(self):
        """有代码内容 → 通过"""
        gate = MemoryGate()
        messages = [
            Message(Role.USER, "show me the code"),
            Message(Role.ASSISTANT, "```python\ndef foo():\n    pass\n```"),
            Message(Role.USER, "what does it do"),
            Message(Role.ASSISTANT, "It defines a function."),
        ]
        result = gate._rule_check(messages)
        assert result.passed is True

    def test_has_error_passes(self):
        """有错误信息 → 通过"""
        gate = MemoryGate()
        messages = [
            Message(Role.USER, "I got an error"),
            Message(Role.ASSISTANT, "Error: something went wrong"),
            Message(Role.USER, "how to fix it"),
            Message(Role.ASSISTANT, "Try reinstalling."),
        ]
        result = gate._rule_check(messages)
        assert result.passed is True


# ── LLM 层测试 ──────────────────────────────────────────────

class TestLLMLayer:
    @pytest.mark.asyncio
    async def test_skip_response(self):
        """LLM 返回 SKIP → 拦截"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "SKIP"
        mock_llm.chat.return_value = mock_response

        gate = MemoryGate(llm=mock_llm)
        messages = [
            Message(Role.USER, "hello there friend"),
            Message(Role.ASSISTANT, "hi!"),
            Message(Role.USER, "how are you doing today"),
            Message(Role.ASSISTANT, "I'm fine!"),
        ]
        result = await gate._llm_evaluate(messages)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_save_response(self):
        """LLM 返回 SAVE 条目 → 通过"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "SAVE|preference|0.8|User prefers concise answers"
        mock_llm.chat.return_value = mock_response

        gate = MemoryGate(llm=mock_llm)
        messages = [
            Message(Role.USER, "keep it short"),
            Message(Role.ASSISTANT, "ok"),
            Message(Role.USER, "really short"),
            Message(Role.ASSISTANT, "understood"),
        ]
        result = await gate._llm_evaluate(messages)
        assert result.passed is True
        assert len(result.entries) == 1
        assert result.entries[0].type == MemoryType.PREFERENCE
        assert result.entries[0].importance == 0.8

    @pytest.mark.asyncio
    async def test_low_importance_filtered(self):
        """importance < 0.4 的条目被丢弃"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "SAVE|fact|0.3|trivial info"
        mock_llm.chat.return_value = mock_response

        gate = MemoryGate(llm=mock_llm)
        messages = [
            Message(Role.USER, "anything new"),
            Message(Role.ASSISTANT, "not really"),
            Message(Role.USER, "ok then"),
            Message(Role.ASSISTANT, "sure"),
        ]
        result = await gate._llm_evaluate(messages)
        assert result.passed is False  # 条目被丢弃后无有效条目


# ── evaluate 集成测试 ───────────────────────────────────────

class TestEvaluate:
    @pytest.mark.asyncio
    async def test_rule_layer_blocks(self):
        """规则层拦截时不调用 LLM"""
        mock_llm = MagicMock()
        gate = MemoryGate(llm=mock_llm)

        messages = [Message(Role.USER, "hi")]
        result = await gate.evaluate(messages)
        assert result.passed is False
        mock_llm.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_llm_passes_rule_only(self):
        """无 LLM 实例时，规则层通过即通过"""
        gate = MemoryGate(llm=None)
        messages = [
            Message(Role.USER, "read the file please"),
            Message(Role.ASSISTANT, [
                {"type": "text", "text": "ok"},
                {"type": "tool_use", "id": "tc1", "name": "file", "input": {}},
            ]),
            Message(Role.USER, [
                {"type": "tool_result", "tool_use_id": "tc1", "content": "content"},
            ]),
        ]
        result = await gate.evaluate(messages)
        assert result.passed is True
