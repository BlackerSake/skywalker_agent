from rich.console import Console
from skywalker.core import AgentState
from skywalker.agent.loop import run_loop
from skywalker.llm.anthropic import AnthropicClient


console = Console()

import sys
from readchar import readkey, key
def read_line_with_ctrlz(prompt: str) -> str | None:
    """使用 readchar 实现CTRL+Z 退出"""
    console.print(prompt, end="")
    sys.stdout.flush() # 确保提示符立即显示
    line = []
    while True:
        ch = readkey()
        if ch == key.CTRL_Z:# 按 CTRL+Z 退出
            console.print()
            return None
        elif ch == key.ENTER:
            console.print()
            break
        elif ch == key.BACKSPACE:
            if line:
                line.pop()
                sys.stdout.write('\b \b')
                sys.stdout.flush()
        elif len(ch) == 1 and ch.isprintable():  # 普通可打印字符
            line.append(ch)
            sys.stdout.write(ch)
            sys.stdout.flush()
        # 可以忽略其他特殊键（方向键等）
    return ''.join(line)


def main():
    console.print("[bold orange1]Skywalker Agent[/bold orange1] - 按下 'Ctrl+Z' 退出\n")

    llm = AnthropicClient()
    state = AgentState()

    while True:
        user_input = read_line_with_ctrlz("[bold blue]You:[/bold blue] ")
        if user_input is None: # 用户按了 CTRL+Z 键
            console.print("已退出,下次见！")
            break

        if user_input.strip().lower() == "exit":
            console.print("下次见！")
            break

        if not user_input.strip():
            continue

        state = run_loop(state, llm, user_input)

        if state.current_response:
            console.print(f"[bold cyan]Agent:[/bold cyan] {state.current_response}\n")

        if state.loop_state.error:
            console.print(f"[bold red]Error:[/bold red] {state.loop_state.error}\n")


if __name__ == "__main__":
    main()