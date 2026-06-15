"""skywalker.tools.web_tool 测试（含 _html_to_text 单元测试）"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from skywalker.tools.base import ToolResult, ToolError
from skywalker.tools.web_tool import WebTool, _html_to_text


# ── _html_to_text ───────────────────────────────────────────

class TestHtmlToText:
    def test_basic_text(self):
        html = "<p>Hello <b>world</b></p>"
        text = _html_to_text(html)
        assert "Hello" in text
        assert "world" in text

    def test_strips_script(self):
        html = "<p>keep</p><script>var x=1;</script><p>also keep</p>"
        text = _html_to_text(html)
        assert "keep" in text
        assert "var x" not in text

    def test_strips_style(self):
        html = "<p>text</p><style>.cls{color:red}</style>"
        text = _html_to_text(html)
        assert "text" in text
        assert "color" not in text

    def test_empty_html(self):
        assert _html_to_text("") == ""


# ── WebTool ─────────────────────────────────────────────────

@pytest.fixture
def tool():
    return WebTool()


class TestWebTool:
    @pytest.mark.asyncio
    async def test_unknown_action(self, tool):
        result = await tool.execute({"action": "nope"})
        assert isinstance(result, ToolError)
        assert result.reason == "execution_error"

    def test_schema(self, tool):
        s = tool.schema()
        assert s["name"] == "web"
        assert "action" in s["input_schema"]["properties"]
        actions = s["input_schema"]["properties"]["action"]["enum"]
        assert "web_search" in actions
        assert "web_fetch" in actions

    @pytest.mark.asyncio
    async def test_web_fetch_mock(self, tool):
        """mock aiohttp，验证 fetch 解析逻辑"""
        mock_resp = AsyncMock()
        mock_resp.text = AsyncMock(return_value="<p>Hello World</p>")
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("skywalker.tools.web_tool.aiohttp", create=True) as mock_aiohttp:
            mock_aiohttp.ClientSession = MagicMock(return_value=mock_session)
            mock_aiohttp.ClientTimeout = MagicMock(return_value=10)
            # 直接 mock _web_fetch 内部的 import
            import sys
            mock_mod = MagicMock()
            mock_mod.ClientSession = MagicMock(return_value=mock_session)
            mock_mod.ClientTimeout = MagicMock(return_value=10)
            with patch.dict(sys.modules, {"aiohttp": mock_mod}):
                result = await tool.execute({"action": "web_fetch", "url": "http://example.com"})
                assert isinstance(result, ToolResult)
                assert "Hello World" in result.output
