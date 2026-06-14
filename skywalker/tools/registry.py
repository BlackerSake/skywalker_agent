
from __future__ import annotations
import logging
from skywalker.tools.base import ToolBase

logger = logging.getLogger(__name__)

class ToolRegistry:
    """管理所有已注册工具，提供按名查找和批量导出 schema 的能力"""
    def __init__(self):
        self._tools: dict[str, ToolBase] = {}

    def register(self, tool: ToolBase) -> None:
        """注册工具，重复注册覆盖并打 warning"""
        if tool.name in self._tools:
            logging.warning(f"⚠️Tool {tool.name} 已经注册")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolBase | None:
        """按名查找，不存在返回 None"""
        return self._tools.get(name)

    def get_schema(self) -> list[dict]:
        """返回所有已注册工具的 schema 列表，顺序与注册顺序一致"""
        return [tool.schema() for tool in self._tools.values()]
    


