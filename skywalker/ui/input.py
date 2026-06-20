from __future__ import annotations

from typing import Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings

_CTRL_Z_PRESSED = object()

# 全局回调，用于 Ctrl+O 触发工具详情展开/折叠
_toggle_callback: Callable[[], None] | None = None


def set_toggle_callback(callback: Callable[[], None]):
    """设置 Ctrl+O 的回调函数"""
    global _toggle_callback
    _toggle_callback = callback


def _create_bindings() -> KeyBindings:
    """创建按键绑定：Ctrl+Z 退出，Ctrl+O 切换工具详情"""
    bindings = KeyBindings()

    @bindings.add("c-z")
    def _(event):
        event.app.exit(result=_CTRL_Z_PRESSED)

    @bindings.add("c-o")
    def _(event):
        if _toggle_callback:
            _toggle_callback()

    return bindings


_BINDINGS = _create_bindings()
_SESSION = PromptSession()


async def read_line(prompt_text: str) -> str | None:
    """使用 prompt_toolkit 异步读取输入，支持退格、方向键、Ctrl+Z 退出"""
    try:
        result = await _SESSION.prompt_async(prompt_text, key_bindings=_BINDINGS)
        if result is _CTRL_Z_PRESSED:
            return None
        return result
    except EOFError:
        return None
    except KeyboardInterrupt:
        return None
