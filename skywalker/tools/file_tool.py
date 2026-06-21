from __future__ import annotations

import difflib
from pathlib import Path

from skywalker.config.settings import settings
from skywalker.tools.base import DiffHunk, FileDiff, ToolBase, ToolError, ToolResult

import logging
logger = logging.getLogger("skywalker.tools")

class ReadFileTool(ToolBase):
    """文件读取工具(只读)"""
    name = "read_file"
    description = "读取文件内容,支持大文件自动截断"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
        },
        "required": ["path"],
    }

    def execute(self, params: dict, tool_call_id: str = "") -> ToolResult | ToolError:
        """统一入口,框架调用方法"""
        path = params.get("path")
        if not path:
            return ToolError(tool_call_id=tool_call_id,
                             error="path is required",
                             reason="need params path"
            ) 
        encoding = params.get("encoding","utf-8")
        return self._read_file(
            path=path,
            encoding=encoding,
        )

    def _read_file(self, path: str) -> ToolResult | ToolError:
        p = Path(path).resolve() # 获取绝对路径
        project = Path(settings.project_root).resolve() # 项目根目录
        
        if not p.is_relative_to(project):  # 检查文件是否在项目根目录内
            return ToolError(tool_call_id="", 
                             error=f"Path outside project root: {path}", 
                             reason="denied")
        if not p.is_file():  # 判断是否是文件
            return ToolError(tool_call_id="", 
                             error=f"Not a file: {path}", 
                             reason="execution_error")
        # 获取文件大小
        try: 
            file_size = p.stat().st_size
        except OSError as e:
            return ToolError(tool_call_id="", 
                             error=f"Cannot stat file{path}: {e}", 
                             reason="execution_error")
        # 读取文件内容
        max_read_size = settings.shell_max_output_tokens * 4
        try:
            if file_size > max_read_size:
                raw = p.read_bytes()[:max_read_size]
                content = raw.decode("utf-8", errors="replace")
                content +=f"\n\n... (File truncated at {max_read_size} bytes, total size: {file_size} bytes)"
            else:
                content = p.read_text(encoding="utf-8")
                truncated = False
        except UnicodeDecodeError:
            return ToolError(tool_call_id="", 
                             error=f"The file: {path} is not utf-8 encoded.", 
                             reason="execution_error")
        except OSError as e: # 文件不存在
            return ToolError(tool_call_id="", 
                             error=f"Failed to  read file: {path}: {e}", 
                             reason="execution_error")
        
        return ToolResult(tool_call_id="", 
                          output=content, 
                          truncated=truncated)

import re
_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@") 

class EditFileTool(ToolBase):
    """文件写入工具：write_file"""
    name = "edit_file"
    description = "文件编辑工具,支持编辑文件内容"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "写入内容"},
        },
        "required": ["path", "content"],
    }

    async def execute(self, params: dict, tool_call_id : str = "") -> ToolResult | ToolError:
        """执行工具"""
        path = params.get("path", "")
        content = params.get("content", "")
        if not path:
            return ToolError(tool_call_id=tool_call_id,
                             error="path is required",
                             reason="need params path"
            )
        if not content:
            return ToolError(tool_call_id=tool_call_id,
                             error="content is required",
                             reason="need params content"
            )
        return self._edit_file(
            path = path, 
            content = content, 
            tool_call_id="")

    def _edit_file(self, path: str, content: str, tool_call_id: str) -> ToolResult | ToolError:
        """编辑文件, 返回结构化diff """
        p = Path(path).resolve()
        project = Path(settings.project_root).resolve()
        # 检查文件是否在项目根目录内
        if not p.is_relative_to(project):
            return ToolError(tool_call_id=tool_call_id, 
                             error=f"Path outside project root: {path}", 
                             reason="denied")

        old_content: str | None = None
        if p.exists():
            try:
                old_content = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                logger.warning(
                    f"The file: {path} is not utf-8 encoded."
                )
            except OSError as e:
                return ToolError(tool_call_id=tool_call_id, 
                                 error=f"Failed to read file: {path}: {e}", 
                                 reason="execution_error")
        # 原子写入文件(唯一 tmp 文件名, 避免并发冲突)
        import uuid
        tmp_id = uuid.uuid4().hex[:8]
        tmp_path = p.with_suffix(p.suffix + f".{tmp_id}.tmp")
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_text(content, encoding="utf-8")
            tmp_path.replace(p)
        except OSError as e:
            tmp_path.unlink(missing_ok=True) # 删除临时文件
            return ToolError(tool_call_id=tool_call_id, 
                             error=f"Failed to write file: {path}: {e}", 
                             reason="execution_error")
        # 获取结果
        if old_content is not None:
            # 获取文件 diff
            file_diff = self._make_file_diff(old_content, content, path)
            return ToolResult(
                tool_call_id=tool_call_id,
                # 输出结果 为 结构化 diff
                output=f"Modified file: {path} (+{file_diff.additions} -{file_diff.deletions})",
                diff=file_diff
                )
    def _make_file_diff(self, old_content: str, new_content: str, path: str) -> FileDiff:
        """生成结构化 diff"""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff_lines = list(
            difflib.unified_diff(old_lines, new_lines, lineterm="", n=3)
        )

        hunks: list[DiffHunk] = []
        current_hunk: DiffHunk | None = None
        additions = 0
        deletions = 0
        
        for line in diff_lines:
            # 忽略 diff 头
            if line.startswith("---") or line.startswith("+++"):
                continue
            if line.startswith("\\"):
                continue 
            
            # 创建新的 hunk
            if line.startswith("@@"):
                if current_hunk:
                    hunks.append(current_hunk)

                match = _HUNK_HEADER_RE.match(line)
                if match:
                    current_hunk = DiffHunk(
                        old_start=int(match.group(1)),
                        new_start=int(match.group(3)),
                        lines=[]
                    )
                else:
                    logger.warning("unexpected hunk header format: %s")
                    current_hunk = None
                continue

            if current_hunk is None:
                continue
            if line.startswith("+"):
                current_hunk.lines.append(("+", line[1:]))
                additions += 1
            elif line.startswith("-"):
                current_hunk.lines.append(("-", line[1:]))
                deletions += 1
            else:
                current_hunk.lines.append((" ", line))
        if current_hunk:
            hunks.append(current_hunk)
        return FileDiff(
            path=path,
            is_new_file=(old_content == ""),
            additions=additions,
            deletions=deletions,
            hunks=hunks
        )



