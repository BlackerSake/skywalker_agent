"""
工具执行的三层防护入口，协调 AST 拦截、权限确认、沙箱执行
"""
from __future__ import annotations

import asyncio
import logging
import re
import time

from skywalker.tools.base import ToolBase, ToolResult, ToolError
from skywalker.tools.registry import ToolRegistry
from skywalker.tools.sandbox import GitWorkTree
from skywalker.config.settings import settings
from skywalker.llm.base import ToolCall

logger = logging.getLogger("skywalker.tools")


class ToolExecutor:
    """工具执行的三层防护入口：AST 拦截 → 权限确认 → 执行"""

    def __init__(self, sandbox: GitWorkTree | None = None):
        self.sandbox = sandbox

    async def run_all(
            self, tool_calls: list[ToolCall], registry: ToolRegistry
    ) -> list[ToolResult | ToolError]:
        """并行执行多个工具调用，每个独立捕获异常"""
        logger.debug(f"⚙️ 批量执行 {len(tool_calls)} 个工具")
        tasks = [self.run_one(tc, registry) for tc in tool_calls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        final: list[ToolResult | ToolError] = []
        for tc, result in zip(tool_calls, results):
            if isinstance(result, Exception):
                logger.error(f"❌ 工具 '{tc.name}' 调用失败: {result}")
                final.append(ToolError(
                    tool_call_id=tc.id,
                    error=str(result),
                    reason="execution_error",
                ))
            else:
                final.append(result)
        return final

    async def run_one(self, tool_call: ToolCall, registry: ToolRegistry) -> ToolResult | ToolError:
        """单个工具调用: 三层防护 + 执行"""
        tool_name = tool_call.name
        logger.debug(f"⏵ 执行工具: {tool_name} | input={tool_call.arguments}")

        # 仅对 shell 类工具做 AST 防护
        if tool_name == "shell" and "command" in tool_call.arguments:
            cmd = tool_call.arguments["command"]
            if self._check_deny(cmd):
                logger.warning(f"🚫 命令被拒绝: {cmd}")
                return ToolError(
                    tool_call_id=tool_call.id,
                    error=f"命令被拒绝: {cmd}",
                    reason="denied",
                )
            if self._check_ask(cmd):
                logger.warning(f"⚠️ 命令需要确认: {cmd}")
                print(f"\n⚠️  Agent 想要运行: {cmd}")
                confirm = input("Allow? (y/n): ").strip().lower()
                if confirm != "y":
                    logger.info(f"🚫 用户拒绝执行: {cmd}")
                    return ToolError(
                        tool_call_id=tool_call.id,
                        error="用户拒绝了命令执行",
                        reason="user_rejected",
                    )

        tool = registry.get(tool_name)
        if tool is None:
            logger.error(f"❌ 工具不存在: {tool_name}")
            return ToolError(
                tool_call_id=tool_call.id,
                error=f"工具 '{tool_name}' 不存在",
                reason="execution_error",
            )

        # 执行并计时
        start_time = time.monotonic()
        try:
            result = await tool.execute(tool_call.arguments)
            elapsed = time.monotonic() - start_time

            if isinstance(result, ToolResult):
                output_preview = result.output[:200] + "..." if len(result.output) > 200 else result.output
                logger.info(f"✅ 工具完成: {tool_name} | 耗时={elapsed:.2f}s | output={output_preview}")
            else:
                logger.warning(f"⚠️ 工具错误: {tool_name} | reason={result.reason} | error={result.error}")

            return result
        except Exception as e:
            elapsed = time.monotonic() - start_time
            logger.error(f"❌ 工具异常: {tool_name} | 耗时={elapsed:.2f}s | error={e}", exc_info=True)
            return ToolError(
                tool_call_id=tool_call.id,
                error=str(e),
                reason="execution_error",
            )

    def _check_deny(self, cmd: str) -> bool:
        """检查命令是否被禁止"""
        return any(re.search(p, cmd) for p in settings.shell_deny_patterns)

    def _check_ask(self, cmd: str) -> bool:
        """检查命令是否需要询问"""
        return any(re.search(p, cmd) for p in settings.shell_ask_patterns)
