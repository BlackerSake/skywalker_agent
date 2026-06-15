"""skywalker.tools.file_tool 测试"""
import pytest
from pathlib import Path
from unittest.mock import patch

from skywalker.tools.base import ToolResult, ToolError
from skywalker.tools.file_tool import FileTool


@pytest.fixture
def tool():
    return FileTool()


@pytest.fixture
def tmp_file(tmp_path):
    """创建一个临时测试文件"""
    f = tmp_path / "test.txt"
    f.write_text("hello world", encoding="utf-8")
    return f


@pytest.fixture
def tmp_dir(tmp_path):
    """创建一个包含子文件的临时目录"""
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.txt").write_text("a")
    (tmp_path / "sub" / "b.txt").write_text("b")
    (tmp_path / "top.txt").write_text("top")
    return tmp_path


# ── read_file ───────────────────────────────────────────────

class TestReadFile:
    @pytest.mark.asyncio
    async def test_read_existing_file(self, tool, tmp_file):
        result = await tool.execute({"action": "read_file", "path": str(tmp_file)})
        assert isinstance(result, ToolResult)
        assert result.output == "hello world"
        assert result.truncated is False

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, tool):
        result = await tool.execute({"action": "read_file", "path": "/no/such/file"})
        assert isinstance(result, ToolError)
        assert result.reason == "execution_error"

    @pytest.mark.asyncio
    async def test_read_directory_returns_error(self, tool, tmp_dir):
        result = await tool.execute({"action": "read_file", "path": str(tmp_dir)})
        assert isinstance(result, ToolError)
        assert "Not a file" in result.error


# ── write_file ──────────────────────────────────────────────

class TestWriteFile:
    @pytest.mark.asyncio
    async def test_write_creates_file(self, tool, tmp_path):
        """mock settings.project_root 为 tmp_path，使路径检查通过"""
        with patch("skywalker.tools.file_tool.settings") as mock_s:
            mock_s.project_root = str(tmp_path)
            mock_s.shell_max_output_tokens = 5000
            target = tmp_path / "new.txt"
            result = await tool.execute({
                "action": "write_file",
                "path": str(target),
                "content": "test content",
            })
            assert isinstance(result, ToolResult)
            assert target.read_text(encoding="utf-8") == "test content"

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self, tool, tmp_path):
        with patch("skywalker.tools.file_tool.settings") as mock_s:
            mock_s.project_root = str(tmp_path)
            mock_s.shell_max_output_tokens = 5000
            target = tmp_path / "a" / "b" / "c.txt"
            result = await tool.execute({
                "action": "write_file",
                "path": str(target),
                "content": "deep",
            })
            assert isinstance(result, ToolResult)
            assert target.read_text(encoding="utf-8") == "deep"


# ── list_dir ────────────────────────────────────────────────

class TestListDir:
    @pytest.mark.asyncio
    async def test_list_dir(self, tool, tmp_dir):
        result = await tool.execute({"action": "list_dir", "path": str(tmp_dir)})
        assert isinstance(result, ToolResult)
        assert "top.txt" in result.output
        assert "sub/" in result.output

    @pytest.mark.asyncio
    async def test_list_nonexistent_dir(self, tool):
        result = await tool.execute({"action": "list_dir", "path": "/no/such/dir"})
        assert isinstance(result, ToolError)
        assert result.reason == "execution_error"


# ── edge cases ──────────────────────────────────────────────

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_unknown_action(self, tool):
        result = await tool.execute({"action": "unknown", "path": "."})
        assert isinstance(result, ToolError)
        assert result.reason == "execution_error"

    def test_schema_structure(self, tool):
        s = tool.schema()
        assert s["name"] == "file"
        assert "action" in s["input_schema"]["properties"]
        assert "path" in s["input_schema"]["properties"]
