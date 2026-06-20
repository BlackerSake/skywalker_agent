from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.completion import WordCompleter
from skywalker.session.store import SessionMeta


async def pick_session(sessions: list[SessionMeta]) -> str | None:
    """交互式选择会话，返回 session_id 或 None（取消）"""
    current = [0]
    def render():
        lines = ["\n历史会话（↑↓ 切换，回车确认，ESC/q 取消，或直接输入 session_id）：\n"]
        for i, s in enumerate(sessions):
            prefix = " > " if i == current[0] else "   "
            row = f"{prefix}{s.title}  ({s.message_count} 条)"
            lines.append(f"\033[7m{row}\033[0m" if i == current[0] else row)
        print("\033[2J\033[H" + "\n".join(lines), end="", flush=True)

    render()
    kb = KeyBindings()

    @kb.add("up")
    def _up(event):
        current[0] = (current[0] - 1) % len(sessions)
        render()

    @kb.add("down")
    def _down(event):
        current[0] = (current[0] + 1) % len(sessions)
        render()

    @kb.add("escape")
    @kb.add("q")
    def _cancel(event):
        event.app.exit(result=None)

    @kb.add("enter")
    def _confirm(event):
        buf = event.app.current_buffer.text.strip()
        event.app.exit(result=buf if buf else sessions[current[0]].session_id)

    ps = PromptSession(
        key_bindings=kb,
        completer=WordCompleter([s.session_id for s in sessions], ignore_case=True),
    )
    try:
        return await ps.prompt_async(HTML("<ansigreen>session_id:</ansigreen> "))
    except (EOFError, KeyboardInterrupt):
        return None
    





