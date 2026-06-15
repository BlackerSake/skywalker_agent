"""skywalker.tools.base 测试"""
import pytest
from abc import ABC

from skywalker.tools.base import ToolBase, ToolResult, ToolError


# ── ToolResult ──────────────────────────────────────────────

class TestToolResult:
    def test_construction(self):
        r = ToolResult(tool_call_id="tc1", output="hello")
        assert r.tool_call_id == "tc1"
        assert r.output == "hello"
        assert r.truncated is False

    def test_truncated_default_false(self):
        r = ToolResult(tool_call_id="", output="")
        assert r.truncated is False

    def test_truncated_set_true(self):
        r = ToolResult(tool_call_id="", output="x", truncated=True)
        assert r.truncated is True


# ── ToolError ───────────────────────────────────────────────

class TestToolError:
    def test_construction(self):
        e = ToolError(tool_call_id="tc2", error="boom", reason="execution_error")
        assert e.tool_call_id == "tc2"
        assert e.error == "boom"
        assert e.reason == "execution_error"

    @pytest.mark.parametrize("reason", ["denied", "timeout", "user_rejected", "execution_error"])
    def test_valid_reasons(self, reason):
        e = ToolError(tool_call_id="", error="", reason=reason)
        assert e.reason == reason


# ── ToolBase ────────────────────────────────────────────────

class TestToolBase:
    def test_cannot_instantiate_abstract(self):
        """ToolBase 是 ABC，不能直接实例化"""
        with pytest.raises(TypeError):
            ToolBase()

    def test_subclass_schema(self):
        """子类实现 schema() 返回正确的 dict"""
        class DummyTool(ToolBase):
            name = "dummy"
            description = "A dummy tool"
            parameters = {"type": "object", "properties": {}}

            async def execute(self, arguments: dict) -> ToolResult | ToolError:
                return ToolResult(tool_call_id="", output="ok")

        tool = DummyTool()
        s = tool.schema()
        assert s["name"] == "dummy"
        assert s["description"] == "A dummy tool"
        assert s["input_schema"] == {"type": "object", "properties": {}}

    @pytest.mark.asyncio
    async def test_subclass_execute(self):
        """子类 execute 返回 ToolResult"""
        class EchoTool(ToolBase):
            name = "echo"
            description = "echo"
            parameters = {}

            async def execute(self, arguments: dict) -> ToolResult | ToolError:
                return ToolResult(tool_call_id=arguments.get("id", ""), output=arguments.get("text", ""))

        tool = EchoTool()
        result = await tool.execute({"id": "tc1", "text": "hello"})
        assert isinstance(result, ToolResult)
        assert result.output == "hello"
        assert result.tool_call_id == "tc1"
