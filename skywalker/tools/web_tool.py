from __future__ import annotations
import asyncio
from html.parser import HTMLParser

from skywalker.tools.base import ToolBase, ToolError, ToolResult


class _HTMLTextExtractor(HTMLParser):
    """HTML 转纯文本的辅助解析器"""
    def __init__(self) -> None:
        super().__init__()
        self._text: list[str] = []
        self._skip = False
    
    
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = False
    
    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._text.append(data)

    def get_text(self) -> str:
        return " ".join(self._text)
    

def _html_to_text(html: str) -> str:
    """将 HTML 转为纯文本"""
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.get_text()

class WebTool(ToolBase):
    """网络检索工具：web_search / web_fetch"""

    name = "web"
    description = "网络工具。支持 web_search（搜索）和 web_fetch（抓取页面内容）。"
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["web_search", "web_fetch"]},
            "query": {"type": "string", "description": "搜索关键词（仅 web_search）"},
            "url": {"type": "string", "description": "目标 URL（仅 web_fetch）"},
            "top_k": {"type": "integer", "description": "返回结果数（仅 web_search，默认 5）"},
        },
        "required": ["action"],
    }

    # 动作映射
    async def execute(self, arguments: dict) -> ToolResult | ToolError:
        action = arguments["action"]
        if action == "web_search":
            return await self._web_search(arguments.get("query", ""), arguments.get("top_k", 5))
        elif action == "web_fetch":
            return await self._web_fetch(arguments.get("url", ""))
        return ToolError(tool_call_id="", error=f"Unknown action: {action}", reason="execution_error")


    async def _web_search(self, query: str, top_k: int = 5) -> ToolResult | ToolError:
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                params = {"q": query, "format": "json", "max_results": top_k}
                async with session.get(
                    "https://api.duckduckgo.com/",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    data = await resp.json(content_type=None)
                    results = data.get("RelatedTopics", [])[:top_k]
                    output = "\n".join(
                        f"- {r.get('Text', '')} ({r.get('FirstURL', '')})"
                        for r in results
                    )
                    return ToolResult(tool_call_id="", output=output or "No results found")
        except Exception as e:
            return ToolError(tool_call_id="", error=str(e), reason="execution_error")

    # 抓取页面内容
    async def _web_fetch(self, url: str) -> ToolResult | ToolError:
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    html = await resp.text()
                    text = _html_to_text(html)
                    if len(text) > 10000:
                        text = text[:10000] + "\n... (truncated)"
                    return ToolResult(tool_call_id="", output=text)
        except Exception as e:
            return ToolError(tool_call_id="", error=str(e), reason="execution_error")








