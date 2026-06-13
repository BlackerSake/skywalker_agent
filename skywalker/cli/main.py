import asyncio
import os
import sys
from pathlib import Path

from rich.console import Console
from readchar import readkey, key

from skywalker.core import AgentState, Message, Role
from skywalker.agent.loop import run_loop
from skywalker.llm.anthropic import AnthropicClient
from skywalker.memory import (
    ConversationManager,
    LLMCompressor,
    LongTermMemory,
    MemoryManager,
)
from skywalker.agent.context import SimpleTokenizer

console = Console()


SKYWALKER_DIR = ".skywalker"
PROJECT_MEMORY_FILE = "MEMORY.md"
USER_MEMORY_FILE = "USER.md"
COMPRESS_THRESHOLD = 0.75
MAX_TOKENS = 8000  # 模型上下文窗口大小


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

def _init_memory(project_root: str):
    """初始化记忆系统"""
    # 记忆目录：{project_root}/.skywalker/
    memory_dir = os.path.join(project_root, SKYWALKER_DIR)

    # 项目记忆路径
    project_memory_path = os.path.join(memory_dir, PROJECT_MEMORY_FILE)
    project_memory = LongTermMemory(project_memory_path)

    # 用户记忆路径
    user_memory_path = os.path.join(memory_dir, USER_MEMORY_FILE)
    user_memory = LongTermMemory(user_memory_path)

    # 压缩器
    llm = AnthropicClient()
    compressor = LLMCompressor(llm)

    # 记忆管理器
    memory_manager = MemoryManager(project_memory, user_memory, compressor)

    return memory_manager, compressor

def _build_system_prompt(memory_manager: MemoryManager) -> str:
    """构建系统提示，注入记忆上下文"""
    base_prompt = "你是一个有用的助手。简洁回答问题。"
    memory_context = memory_manager.get_system_context()
    if memory_context:
        return f"{base_prompt}\n\n{memory_context}"
    return base_prompt


def main():
    console.print("[bold orange1]Skywalker Agent[/bold orange1] - 按下 'Ctrl+Z' 退出\n")

    # 获取项目根目录
    project_root = os.getcwd()

    # 初始化记忆系统
    memory_manager, compressor = _init_memory(project_root)

    # 加载记忆并显示
    project_entries = memory_manager._project_memory.load()
    user_entries = memory_manager._user_memory.load()
    total = len(project_entries) + len(user_entries)
    console.print(f"[dim]已加载 {total} 条记忆（项目：{len(project_entries)}，用户：{len(user_entries)}）[/dim]\n")

    # 初始化 LLM 和会话管理器
    llm = AnthropicClient()
    conv_manager = ConversationManager(
        compressor=compressor,
        max_tokens=MAX_TOKENS,
        compress_threshold=COMPRESS_THRESHOLD,
    )

    # 构建带记忆的系统提示
    system_prompt = _build_system_prompt(memory_manager)

    state = AgentState(project_root=project_root)

    while True:
        user_input = read_line_with_ctrlz("[bold blue]You:[/bold blue] ")
        if user_input is None:
            # shutdown 时写回记忆
            loop = asyncio.new_event_loop()
            saved = loop.run_until_complete(memory_manager.on_shutdown(state))
            loop.close()
            if saved:
                console.print("已退出，记忆已保存！")
            else:
                console.print("已退出。")
            break

        if user_input.strip().lower() == "exit":
            loop = asyncio.new_event_loop()
            saved = loop.run_until_complete(memory_manager.on_shutdown(state))
            loop.close()
            if saved:
                console.print("记忆已保存！")
            else:
                console.print("已退出。")
            break

        if not user_input.strip():
            continue

        # 添加用户消息到会话管理器
        user_msg = Message(Role.USER, user_input)
        conv_manager.add_message(user_msg)
        state.messages.append(user_msg)

        # 检查是否需要压缩
        if conv_manager.should_compress():
            console.print("[dim]正在压缩历史消息...[/dim]")
            loop = asyncio.new_event_loop()
            loop.run_until_complete(conv_manager.compress())
            loop.close()
            # 同步压缩后的消息到 state
            state.messages = conv_manager.messages

        # 调用 LLM
        try:
            response = llm.chat(conv_manager.messages, system=system_prompt)
            assistant_msg = Message(Role.ASSISTANT, response)
            conv_manager.add_message(assistant_msg)
            state.messages.append(assistant_msg)
            state.current_response = response
        except Exception as e:
            state.loop_state.error = str(e)
            console.print(f"[bold red]Error:[/bold red] {e}\n")
            continue

        if state.current_response:
            console.print(f"[bold cyan]Agent:[/bold cyan] {state.current_response}\n")


if __name__ == "__main__":
    main()