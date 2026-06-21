from __future__ import annotations

import difflib
from pathlib import Path

from skywalker.config.settings import settings
from skywalker.tools.base import DiffHunk, FileDiff, ToolBase, ToolError, ToolResult


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
        return ToolError(tool_call_id="", error=f"未知 action: {action}", reason="execution_error")

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
        """写入文件，生成结构化 diff"""
        p = Path(path).resolve()
        project = Path(settings.project_root).resolve()
        if not str(p).startswith(str(project)):
            return ToolError(tool_call_id="", error=f"Path outside project root: {path}", reason="denied")

        p.parent.mkdir(parents=True, exist_ok=True)

        # 读取旧内容
        old_content = ""
        if p.exists():
            old_content = p.read_text(encoding="utf-8")

        # 写入新内容
        p.write_text(content, encoding="utf-8")

        # 生成结构化 diff
        if old_content:
            file_diff = self._make_file_diff(old_content, content, path)
            return ToolResult(
                tool_call_id="",
                output=f"Modified {path} (+{file_diff.additions} -{file_diff.deletions})",
                diff=file_diff,
            )
        else:
            return ToolResult(tool_call_id="", output=f"Created {path} ({len(content)} chars)")

    def _make_file_diff(self, old: str, new: str, path: str) -> FileDiff:
        """生成结构化 FileDiff 对象"""
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)

        # 用 difflib 生成 unified diff（n=3 控制上下文行数）
        diff_lines = list(difflib.unified_diff(
            old_lines, new_lines,
            lineterm="",
            n=3,
        ))

        # 解析为结构化 hunks
        hunks = []
        current_hunk = None
        old_line = 0
        new_line = 0
        additions = 0
        deletions = 0

        for line in diff_lines:
            if line.startswith("@@"):
                # 解析 @@ -a,b +c,d @@
                import re
                match = re.search(r"-(\d+).+\+(\d+)", line)
                if match:
                    old_line = int(match.group(1))
                    new_line = int(match.group(2))
                if current_hunk:
                    hunks.append(current_hunk)
                current_hunk = DiffHunk(old_start=old_line, new_start=new_line, lines=[])
            elif line.startswith("+"):
                if current_hunk:
                    current_hunk.lines.append(("+", line[1:]))
                additions += 1
            elif line.startswith("-"):
                if current_hunk:
                    current_hunk.lines.append(("-", line[1:]))
                deletions += 1
            elif not line.startswith("---") and not line.startswith("+++"):
                if current_hunk:
                    current_hunk.lines.append((" ", line))

        if current_hunk:
            hunks.append(current_hunk)

        return FileDiff(
            path=path,
            is_new_file=False,
            additions=additions,
            deletions=deletions,
            hunks=hunks,
        )

    def _list_dir(self, path: str, max_depth: int = 3) -> ToolResult | ToolError:
        p = Path(path).resolve()
        if not p.exists():
            return ToolError(tool_call_id="", error=f"Directory not found: {path}", reason="execution_error")
        lines = []
        for item in sorted(p.rglob("*")):
            depth = len(item.relative_to(p).parts)
            if depth > max_depth:
                continue
            indent = "  " * depth
            lines.append(f"{indent}{item.name}{'/' if item.is_dir() else ''}")
        return ToolResult(tool_call_id="", output="\n".join(lines))
