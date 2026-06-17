from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings

_CTRL_Z_PRESSED = object()

def _create_bindings() -> KeyBindings:
    """创建按键绑定：Ctrl+Z 退出"""
    bindings = KeyBindings()

    @bindings.add("c-z")
    def _(event):
        event.app.exit(result=_CTRL_Z_PRESSED)

    return bindings

_BINDINGS = _create_bindings()

_SESSION = PromptSession()


async def read_line_with_ctrlz(prompt_text: str) -> str | None:
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
    
