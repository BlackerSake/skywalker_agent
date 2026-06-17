import asyncio
import json
import logging
import os

from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.shortcuts import PromptSession
from rich.console import Console

from config.logging import setup_logging
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
from skywalker.ui.input import read_line
from skywalker.ui.output import OutputRenderer

logger = logging.getLogger("skywalker")


console = Console()
session = PromptSession()

SKYWALKER_DIR = ".skywalker"
PROJECT_MEMORY_FILE = "MEMORY.md"
USER_MEMORY_FILE = "USER.md"
COMPRESS_THRESHOLD = 0.75
MAX_TOKENS = 8000


# Ctrl+Z 退出的标记
_CTRL_Z_PRESSED = object()


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
    # 初始化日志系统
    setup_logging(debug=True)
    logger.info("=" * 50)
    logger.info("🚀 Skywalker Agent 启动")

    renderer = OutputRenderer(style="default")
    renderer.console.print("[bold orange1]Skywalker Agent[/] - 按下 'Ctrl+Z' 退出\n")

    project_root = os.getcwd()
    llm = AnthropicClient()

    # 初始化记忆系统并加载
    memory_manager, compressor = _init_memory(project_root, llm)

    project_entries = memory_manager._project_memory.load()
    user_entries = memory_manager._user_memory.load()
    total = len(project_entries) + len(user_entries)
    renderer.console.print(f"[dim]已加载 {total} 条记忆（项目：{len(project_entries)}，用户：{len(user_entries)}）[/]\n")

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
    renderer.console.print(f"[dim]已创建会话 {session_id}[/]\n")

    state = AgentState(project_root=project_root)

    while True:
        user_input = await read_line(HTML("<ansiblue><b>You:</b></ansiblue> "))
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

            # 恢复会话后同步 conv_manager
            if result.resumed_messages is not None:
                conv_manager.clear()
                for msg in result.resumed_messages:
                    conv_manager.add_message(msg)

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

        # 显示 Thinking Spinner
        renderer.show_thinking()

        # 运行 loop（内部处理 LLM 调用、工具执行、压缩检查）
        state = await run_loop(
            state, llm, user_input,
            conv_manager=conv_manager,
            memory_manager=memory_manager,
            system_prompt=system_prompt,
            registry=registry,
            executor=executor,
            on_event=renderer.render_event,  # 事件回调
        )

        if state.current_response:
            # 同步 assistant 回复到 session_manager
            assistant_msg = Message(Role.ASSISTANT, state.current_response)
            session_manager.add_message(assistant_msg)

        if state.loop_state.error:
            renderer.console.print(f"[bold red]Error: {state.loop_state.error}[/]\n")


def cli_main():
    """同步入口点，供 pyproject.toml entry_points 调用"""
    asyncio.run(main())


if __name__ == "__main__":
    cli_main()
