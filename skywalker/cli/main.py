import asyncio
import json
import os

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console

from skywalker.commands.builtin import register_builtin_commands
from skywalker.commands.registry import CommandRegistry
from skywalker.session.manager import SessionManager
from skywalker.session.store import SessionStore
from skywalker.config.settings import settings
from skywalker.core import AgentState, Message, Role
from skywalker.agent.loop import run_loop, shutdown
from skywalker.llm.anthropic import AnthropicClient
from skywalker.memory import (
    ConversationManager,
    LLMCompressor,
    LongTermMemory,
    MemoryGate,
    MemoryManager,
)
from skywalker.tools import (
    FileTool, GitWorkTree, ShellTool, ToolExecutor, ToolRegistry, WebTool,
)

console = Console()
session = PromptSession()

SKYWALKER_DIR = ".skywalker"
PROJECT_MEMORY_FILE = "MEMORY.md"
USER_MEMORY_FILE = "USER.md"
COMPRESS_THRESHOLD = 0.75
MAX_TOKENS = 8000


# Ctrl+Z 退出的标记
_CTRL_Z_PRESSED = object()


def _create_bindings() -> KeyBindings:
    """创建按键绑定：Ctrl+Z 退出"""
    bindings = KeyBindings()

    @bindings.add("c-z")
    def _(event):
        event.app.exit(result=_CTRL_Z_PRESSED)

    return bindings


_BINDINGS = _create_bindings()


async def read_line_with_ctrlz(prompt_text: str) -> str | None:
    """使用 prompt_toolkit 异步读取输入，支持退格、方向键、Ctrl+Z 退出"""
    try:
        result = await session.prompt_async(prompt_text, key_bindings=_BINDINGS)
        if result is _CTRL_Z_PRESSED:
            return None
        return result
    except EOFError:
        return None
    except KeyboardInterrupt:
        return None


def print_msg(text: str, style: str = ""):
    """打印消息，支持简单的颜色标记"""
    colors = {
        "bold blue": "\033[1;34m",
        "bold cyan": "\033[1;36m",
        "bold orange1": "\033[1;33m",
        "bold red": "\033[1;31m",
        "dim": "\033[2m",
    }
    reset = "\033[0m"

    if style and style in colors:
        print(f"{colors[style]}{text}{reset}", end="")
    else:
        print(text, end="")


def _init_memory(project_root: str, llm: AnthropicClient):
    """初始化记忆系统，复用传入的 llm 实例"""
    memory_dir = os.path.join(project_root, SKYWALKER_DIR)
    os.makedirs(memory_dir, exist_ok=True)

    project_memory_path = os.path.join(memory_dir, PROJECT_MEMORY_FILE)
    project_memory = LongTermMemory(project_memory_path)

    user_memory_path = os.path.expanduser("/Alpha/College_new/skywalker_agent/.skywalker/user/USER.md")
    os.makedirs(os.path.dirname(user_memory_path), exist_ok=True)
    user_memory = LongTermMemory(user_memory_path)

    compressor = LLMCompressor(llm)
    gate = MemoryGate(llm=llm)
    memory_manager = MemoryManager(project_memory, user_memory, compressor, gate=gate)

    return memory_manager, compressor


def _init_tools(project_root: str) -> tuple[ToolRegistry, ToolExecutor]:
    """初始化工具系统"""
    registry = ToolRegistry()
    registry.register(FileTool())
    registry.register(ShellTool())
    registry.register(WebTool())

    sandbox = GitWorkTree(project_root) if settings.sandbox_enabled else None
    executor = ToolExecutor(sandbox=sandbox)
    return registry, executor

def _init_session(memory_manager: MemoryManager) -> tuple[SessionManager, CommandRegistry]:
    """初始化会话系统 和 命令系统"""
    store = SessionStore()
    session_manager = SessionManager(store, memory_manager)
    registry = CommandRegistry()
    register_builtin_commands(registry, session_manager, memory_manager)

    return store, session_manager, registry



def _build_system_prompt(memory_manager: MemoryManager, registry: ToolRegistry | None = None) -> str:
    """构建系统提示，注入记忆上下文 + tool schema"""
    base_prompt = "你是一个有用的助手。简洁回答问题。"
    memory_context = memory_manager.get_system_context()
    system_prompt = f"{base_prompt}\n\n{memory_context}" if memory_context else base_prompt

    if registry:
        schemas = registry.get_schema()
        if schemas:
            tool_section = "\n\n## Available Tools\n" + json.dumps(schemas, indent=2, ensure_ascii=False)
            system_prompt += tool_section
    return system_prompt


async def main():
    print_msg("Skywalker Agent", "bold orange1")
    print(" - 按下 'Ctrl+Z' 退出\n")

    project_root = os.getcwd()
    llm = AnthropicClient()

    # 初始化记忆系统并加载
    memory_manager, compressor = _init_memory(project_root, llm)

    project_entries = memory_manager._project_memory.load()
    user_entries = memory_manager._user_memory.load()
    total = len(project_entries) + len(user_entries)
    print_msg(f"已加载 {total} 条记忆（项目：{len(project_entries)}，用户：{len(user_entries)}）\n", "dim")

    # 初始化会话管理器
    conv_manager = ConversationManager(
        compressor=compressor,
        max_tokens=MAX_TOKENS,
        compress_threshold=COMPRESS_THRESHOLD,
    )

    # 初始化工具
    registry, executor = _init_tools(project_root)

    # 构建带记忆和工具的系统提示
    system_prompt = _build_system_prompt(memory_manager, registry)

    # 初始化会话状态和命令系统
    store, session_manager, command_registry = _init_session(memory_manager)
    
    # 新建会话
    session_id = session_manager.new_session(project_root)
    print_msg(f"已创建会话 {session_id}\n", "dim")

    state = AgentState(project_root=project_root)

    while True:
        user_input = await read_line_with_ctrlz(HTML("<ansiblue><b>You:</b></ansiblue> "))
        if user_input is None:
            # Ctrl+Z 退出：保存会话 + 记忆
            await session_manager.save_session()
            saved = await memory_manager.on_shutdown(state)
            if saved:
                print("已退出，会话和记忆已保存！")
            else:
                print("已退出，会话已保存。")
            break

        if user_input.strip().lower() == "exit":
            # exit 退出：保存会话 + 记忆
            await session_manager.save_session()
            saved = await memory_manager.on_shutdown(state)
            if saved:
                print("会话和记忆已保存！")
            else:
                print("会话已保存。")
            break

        if user_input.strip().startswith("/"):
            # /exit 直接走退出流程
            if user_input.strip() == "/exit":
                await session_manager.save_session()
                saved = await memory_manager.on_shutdown(state)
                print("会话已保存，再见！")
                break
            result = await command_registry.dispatch(user_input, state)
            if result.output:
                print(result.output)
            if not result.should_complete:
                break
            continue

        if not user_input.strip():
            continue

        # 添加用户消息到会话管理器（同步到三个地方）
        user_msg = Message(Role.USER, user_input)
        conv_manager.add_message(user_msg)
        state.messages.append(user_msg)
        session_manager.add_message(user_msg)

        # 运行 loop（内部处理 LLM 调用、工具执行、压缩检查）
        state = await run_loop(
            state, llm, user_input,
            conv_manager=conv_manager,
            memory_manager=memory_manager,
            system_prompt=system_prompt,
            registry=registry,
            executor=executor,
        )

        if state.current_response:
            # 同步 assistant 回复到 session_manager
            assistant_msg = Message(Role.ASSISTANT, state.current_response)
            session_manager.add_message(assistant_msg)
            print_msg("Agent: ", "bold cyan")
            print(f"{state.current_response}\n")

        if state.loop_state.error:
            print_msg(f"Error: {state.loop_state.error}\n\n", "bold red")


def cli_main():
    """同步入口点，供 pyproject.toml entry_points 调用"""
    asyncio.run(main())


if __name__ == "__main__":
    cli_main()
