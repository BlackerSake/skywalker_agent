"""skywalker.tools.registry 测试"""
import pytest

from skywalker.tools.base import ToolBase, ToolResult, ToolError
from skywalker.tools.registry import ToolRegistry


def _make_tool(name: str) -> ToolBase:
    """构造一个简单的测试工具"""
    class _T(ToolBase):
        async def execute(self, arguments: dict) -> ToolResult | ToolError:
            return ToolResult(tool_call_id="", output=name)

    t = _T()
    t.name = name
    t.description = f"{name} tool"
    t.parameters = {"type": "object", "properties": {}}
    return t


class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        tool = _make_tool("alpha")
        reg.register(tool)
        assert reg.get("alpha") is tool

    def test_get_nonexistent_returns_none(self):
        reg = ToolRegistry()
        assert reg.get("no_such_tool") is None

    def test_register_overwrites(self, caplog):
        """重复注册覆盖旧对象，不抛异常"""
        reg = ToolRegistry()
        t1 = _make_tool("x")
        t2 = _make_tool("x")
        reg.register(t1)
        reg.register(t2)
        assert reg.get("x") is t2

    def test_get_schemas_empty(self):
        reg = ToolRegistry()
        assert reg.get_schema() == []

    def test_get_schemas_returns_all(self):
        reg = ToolRegistry()
        reg.register(_make_tool("a"))
        reg.register(_make_tool("b"))
        schemas = reg.get_schema()
        assert len(schemas) == 2
        names = [s["name"] for s in schemas]
        assert "a" in names
        assert "b" in names

    def test_get_schemas_order_matches_registration(self):
        reg = ToolRegistry()
        reg.register(_make_tool("first"))
        reg.register(_make_tool("second"))
        schemas = reg.get_schema()
        assert schemas[0]["name"] == "first"
        assert schemas[1]["name"] == "second"
