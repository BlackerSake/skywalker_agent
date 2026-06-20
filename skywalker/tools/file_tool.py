from __future__ import annotations

from pathlib import Path

from skywalker.config.settings import settings
from skywalker.tools.base import ToolBase, ToolError, ToolResult

"""封装文件读写操作，提供 read_file / write_file / list_dir 三个原子操作"""


class FileTool(ToolBase):
    """文件操作工具：read_file / write_file / list_dir"""
    name = "file"
    description = "文件操作工具。支持 read_file（读取文件内容）、write_file（写入文件）、list_dir（列出目录）。"
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["read_file", "write_file", "list_dir"]},
            "path": {"type": "string", "description": "文件或目录路径"},
            "content": {"type": "string", "description": "写入内容（仅 write_file 需要）"},
        },
        "required": ["action", "path"],
    }

    async def execute(self, arguments: dict) -> ToolResult | ToolError:
        """根据 action 分发到具体方法"""
        action = arguments["action"]
        path = arguments["path"]
        if action == "read_file":
            return self._read_file(path)
        elif action == "write_file":
            return self._write_file(path, arguments.get("content", ""))
        elif action == "list_dir":
            return self._list_dir(path)
        return ToolError(tool_call_id="", error=f"未知 行动: {action}", reason="execution_error")


    def _read_file(self, path: str) -> ToolResult | ToolError:
        """读取文件"""
        p = Path(path).resolve()
        if not p.exists():
            return ToolError(tool_call_id="", error=f"File not found: {path}", reason="execution_error")
        if not p.is_file():
            return ToolError(tool_call_id="", error=f"Not a file: {path}", reason="execution_error")
        content = p.read_text(encoding="utf-8")
        truncated = False
        if len(content) > settings.shell_max_output_tokens * 3:
            content = content[:settings.shell_max_output_tokens * 3]
            truncated = True
        return ToolResult(tool_call_id="", output=content, truncated=truncated)

    def _write_file(self, path: str, content: str) -> ToolResult | ToolError:
        p = Path(path).resolve()
        # 路径越界检查：必须在 project_root 内
        project = Path(settings.project_root).resolve()
        if not str(p).startswith(str(project)):
            return ToolError(tool_call_id="", error=f"Path outside project root: {path}", reason="denied")

        # 确保目录存在
        p.parent.mkdir(parents=True, exist_ok=True)

        # 读取旧内容
        old_content = ""
        if p.exists():
            old_content = p.read_text(encoding="utf-8")

        # 写入新内容
        p.write_text(content, encoding="utf-8")

        # 生成 diff
        if old_content:
            diff = self._make_diff(old_content, content, path)
            return ToolResult(tool_call_id="", output=diff)
        else:
            return ToolResult(tool_call_id="", output=f"Created {path} ({len(content)} chars)")
    
    def _make_diff(self, old: str, new: str, path: str) -> str:
        """生成 unified diff"""
        import difflib
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
        return "".join(diff)
    
    def _list_dir(self, path: str, max_depth: int = 3) -> ToolResult | ToolError:
        p = Path(path).resolve()
        if not p.exists():
            return ToolError(
                tool_call_id="", error=f"Directory not found: {path}", reason="execution_error"
            )
        lines = []
        for item in sorted(p.rglob("*")):
            depth = len(item.relative_to(p).parts)
            if depth > max_depth:
                continue
            indent = "  " * depth
            lines.append(f"{indent}{item.name}{'/' if item.is_dir() else ''}")
        return ToolResult(tool_call_id="", output="\n".join(lines))
