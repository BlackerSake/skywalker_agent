"""
工具执行的三层防护入口，协调 AST 拦截、权限确认、沙箱执行
"""
from __future__ import annotations
import asyncio
from os import error
import re
import logging
from unittest import result
from skywalker.tools.base import ToolBase, ToolResult, ToolError
from skywalker.tools.registry import ToolRegistry
from skywalker.tools.sandbox import GitWorktree
from skywalker.config.settings import settings
from skywalker.llm.base import ToolCall

logger = logging.getLogger(__name__)

class ToolExecutor:
    """工具执行的三层防护入口：AST 拦截 → 权限确认 → 执行"""
    def __init__(self, sandbox: GitWorktree | None = None):
        self.sandbox = sandbox
    async def run_all(
            self, tool_calls: list[ToolCall], registry: ToolRegistry
    ) -> list[ToolResult | ToolError]:
        """并行执行多个工具调用，每个独立捕获异常"""
        tasks = [self.run_one(tc, registry) for tc in tool_calls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        final: list[ToolResult | ToolError] = []
        for tc, results in zip(tool_calls, results):
            if isinstance(results, Exception):
                logger.error(f"Tool '{tc.name}' 调用失败: {results}")
                final.append(tool_call_id = tc.id, error = str(result),reason="execution_error")
            else:
                final.append(results)
        return final
    async def run_one(self, tool_call: ToolCall, registry: ToolRegistry) -> ToolResult | ToolError:
        """单个工具调用: 三层防护 + 执行"""
        # 仅对 shell 类工具做 AST 防护
        if tool_call.name == "shell" and "command" in tool_call.arguments:
            cmd = tool_call.arguments["command"]
            if self._check_deny(cmd):
                return ToolError(
                    tool_call_id=tool_call.id,
                    error=f"命令 取消: {cmd}",
                    reason="denied",
                )
            if self._check_ask(cmd):
                print(f"\n⚠️  Agent 想要运行 : {cmd}")
                confirm = input("Allow? (y/n): ").strip().lower()
                if confirm != "y":
                    return ToolError(
                        tool_call_id=tool_call.id,
                        error="用户 拒绝了命令执行",
                        reason="user_rejected",
                    )
        tool = registry.get(tool_call.name)
        if tool is None:
            return ToolError(
                tool_call_id=tool_call.id,
                error=f"工具 '{tool_call.name}' 不存在",
                reason="execution_error",
            )
        return await tool.execute(tool_call.arguments)
    def _check_deny(self, cmd: str) -> bool:
        """检查命令是否被禁止"""
        return any(re.search(p,cmd) for p in settings.shell_deny_patterns)
    def _check_ask(self, cmd: str) -> bool:
        """检查命令是否需要询问"""
        return any(re.search(p,cmd) for p in settings.shell_ask_patterns)
