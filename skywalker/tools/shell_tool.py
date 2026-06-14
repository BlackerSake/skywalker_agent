
from __future__ import annotations

import asyncio

from skywalker.config.settings import settings
from skywalker.tools.base import ToolBase, ToolError, ToolResult

class ShellTool(ToolBase):
    """Shell 命令执行工具"""
    name = "shell"
    description = "执行Shell命令,返回exit_code和stdout和stderr"
    parameters = {
    "type": "object",
    "properties": {
        "command": {"type": "string", "description": "要执行的 shell 命令"},
    },
    "required": ["command"],
    }

    async def execute(self, arguments: dict) -> ToolResult | ToolError:
        cmd = arguments["command"]
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=settings.tool_timeout
            )
            exit_code = proc.returncode
            output = f"exit_code: {exit_code}\n"
            if stdout:
                output += f"stdout:\n{stdout.decode()}\n"
            if stderr:
                output += f"stderr:\n{stderr.decode()}\n"
            if len(output) > settings.shell_max_output_tokens * 3:
                output = output[:settings.shell_max_output_tokens * 3] + "\n... (truncated)"
            return ToolResult(tool_call_id="", output=output)
        except asyncio.TimeoutError:
            proc.kill()
            return ToolError(
                tool_call_id="",
                error=f"Command timed out after {settings.tool_timeout}s",
                reason="timeout",
            )



