
"""工具执行的三层防护入口，协调 AST 拦截、权限确认、沙箱执行"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Callable, Awaitable

from skywalker.tools.base import ToolBase, ToolResult, ToolError
from skywalker.tools.registry import ToolRegistry
from skywalker.tools.sandbox import GitWorkTree
from skywalker.config.settings import settings
from skywalker.llm.base import ToolCall

logger = logging.getLogger("skywalker.tools")

# 确认回调类型：接收命令字符串，返回是否允许
ConfirmCallback = Callable[[str], bool]


class ToolExecutor:
    """工具执行的三层防护入口：AST 拦截 → 权限确认 → 执行"""

    def __init__(self, sandbox: GitWorkTree | None = None,
                 confirm_callback: ConfirmCallback | None = None,
                 shadow_repo =  None):
        self.sandbox = sandbox
        self._confirm_callback = confirm_callback
        self._shadow_repo = shadow_repo
        self._complied_deny: list[re.Pattern] = []
        self._complied_ask: list[re.Pattern] = []
        self._complie_patterns()

    # --- 初始化
    def _complie_patterns(self):
        """预编译正则模式, 避免每次都调用重复编译"""
        self._complied_deny = [re.compile(p) for p in settings.shell_deny_patterns]
        self._complied_ask = [re.compile(p) for p in settings.shell_ask_patterns]

    def reload_patterns(self):
        """配置热更新后 重新编译模式"""
        self._complie_patterns()
    
    # ---批量执行工具
    async def run_all(self, tool_calls: list[ToolCall],
                      tool_registry: ToolRegistry) -> list[ToolResult | ToolError]:
        if not tool_calls:
            return []
        logger.debug("批量调用工具 %d 个", len(tool_calls))

        tasks = [self.run_one(tc, tool_registry) for tc in tool_calls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 长度校验: gather 返回的列表长度必须与 tool_calls 一样长
        assert len(results) == len(tool_calls)

        final: list[ToolResult | ToolError] = []
        # 批量处理结果
        for tc, result in zip(tool_calls, results):
            if isinstance(result, BaseException):
                logger.error("❌ 工具'%s'调用异常: %s", tc.name, result)
                final.append(ToolError(
                    tool_call_id=tc.id,
                    error=str(result),
                    reason="execution_error"
                ))
            else:
                final.append(result)
        return final
    # --- 单个执行工具
    async def run_one(self, tool_call: ToolCall, tool_registry: ToolRegistry) -> ToolResult | ToolError:
        """单个工具调用: 三层防护 + 执行"""
        tool_name = tool_call.name
        tool_call_id = tool_call.id
        logger.debug("执行 tool: %s | input=%s", tool_name, tool_call.arguments)

        # --- 第一层: AST 拦截(对于 shell tool)
        if tool_name == "shell" and "command" in tool_call.arguments:
            cmd = tool_call.arguments["command"]
            # 拦截
            block_result = await self._check_command_block(cmd, tool_call_id)
            if block_result is not None:
                return block_result
        
        # --- 第二层: tool 查找
        tool = tool_registry.get(tool_name)
        if tool is None:
            logger.warning("❌ 工具'%s'不存在", tool_name)
            return ToolError(
                tool_call_id=tool_call_id,
                error="tool '{tool_name}' not found",
                reason="tool_not_found"
            )
        # --- 第三层: 执行(带计时与异常保护)
        exec_result = time.monotonic() # 计时开始
        try:
            result = await self._execute_with_shadow(tool, tool_call)
        except Exception as e:
            elapsed = time.monotonic() - exec_result
            logger.error("❌ 工具'%s'执行 '%.2f's 后异常: %s", tool_name, elapsed, e, exc_info=True)
            return ToolError(
                tool_call_id=tool_call_id,
                error=str(e),
                reason="execution_error"
            )
        elapsed = time.monotonic() - exec_result
        logger.debug("✅ 命令'%s'执行 '%.2f's 后完成", tool_name, elapsed)
        
        return result


    # --- 命令拦截

    async def _check_command_block(self, cmd: str, tool_call_id: str) -> ToolError | None:
        """检查命令是否被拦截, ToolError 表示拦截, None表示通过"""
        if any(p.search(cmd) for p in self._complied_deny):
            logger.warning("❌ 工具'shell'调用被拦截: %s", cmd)
            return ToolError(
                tool_call_id=tool_call_id,
                error="command_blocked:{cmd}",
                reason="denied"
            )
        if any(p.search(cmd) for p in self._complied_ask):
            logger.warning("⚠️ 命令'%s'可能存在问题，请确认是否需要执行:", cmd)
            if self._confirm_callback is not None:
                allowed = await self._invoke_callback(cmd)
                if not allowed:
                    logger.info("用户拒绝执行命令: %s", cmd)
                    return ToolError(
                        tool_call_id=tool_call_id,
                        error="user rejected the cmd",
                        reason="user_rejected"
                    )
        return None
    async def _invoke_callback(self, cmd: str) -> bool:
        """调用用户确认回调, 返回是否允许执行"""
        if self._confirm_callback is None:
            return True
        result = await self._confirm_callback(cmd)

        # 兼容异步回调
        if asyncio.iscoroutine(result) or asyncio.isfuture(result):
            result = await result
        return bool(result)
    
    # --- 执行工具
    async def _execute_with_shadow(self, tool: ToolBase, tool_call: ToolCall) -> ToolResult | ToolError:
        """执行工具, 如果带有shadowrepo, 则包裹快照跟踪"""
        async def do_execute():
            return await tool.execute(tool_call.arguments)
        if self._shadow_repo:
            result, diff = await self._shadow_repo.track(do_execute, tool_call.id)

            if isinstance(result, ToolResult) and diff is not None:
                result.diff = diff
                logger.debug(f"📝 Diff 生成: {tool_call.name} | diff={type(diff).__name__}")
            else:
                logger.debug(f"📝 无 Diff: {tool_call.name} | diff={diff}")
            return result
        return await do_execute()
    
    # ---正则匹配
    def _check_deny(self, cmd: str) -> bool:
        """检查命令是否被拦截"""
        return any(p.search(cmd) for p in self._complied_deny)
    def _check_ask(self, cmd: str) -> bool:
        """检查命令是否需要确认"""
        return any(p.search(cmd) for p in self._complied_ask)