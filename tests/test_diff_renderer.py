"""diff_renderer 测试"""

import pytest
import re
from io import StringIO
from rich.console import Console

from skywalker.ui.diff_renderer import render_diff


def strip_ansi(text: str) -> str:
    """去除 ANSI 转义序列"""
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


def test_render_diff():
    """测试 diff 渲染"""
    diff_text = """--- a/config.yaml
+++ b/config.yaml
@@ -1,5 +1,6 @@
 name: skywalker
-version: 3.6
+version: 3.6.1
 debug: false
+log_level: info
 description: CLI Agent"""

    output = StringIO()
    console = Console(file=output, force_terminal=True)
    render_diff(console, diff_text)

    result = strip_ansi(output.getvalue())
    assert "+2" in result
    assert "-1" in result
    assert "lines changed" in result
    assert "version: 3.6.1" in result
    assert "log_level: info" in result


def test_render_diff_new_file():
    """测试新建文件（只有新增）"""
    diff_text = """--- /dev/null
+++ b/new_file.py
@@ -0,0 +1,3 @@
+def hello():
+    return "world"
+"""

    output = StringIO()
    console = Console(file=output, force_terminal=True)
    render_diff(console, diff_text)

    result = strip_ansi(output.getvalue())
    assert "+3" in result
    assert "lines changed" in result


def test_render_diff_empty():
    """测试空 diff"""
    diff_text = ""

    output = StringIO()
    console = Console(file=output, force_terminal=True)
    render_diff(console, diff_text)

    result = output.getvalue()
    assert "lines changed" not in result


def test_render_diff_with_line_numbers():
    """测试行号显示"""
    diff_text = """--- a/test.py
+++ b/test.py
@@ -10,3 +10,4 @@
 def foo():
     pass
+
 def bar():
"""

    output = StringIO()
    console = Console(file=output, force_terminal=True)
    render_diff(console, diff_text)

    result = strip_ansi(output.getvalue())
    # 检查行号存在
    assert "10" in result
    assert "11" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
