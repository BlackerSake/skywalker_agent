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
from skywalker.ui.input import read_line, set_toggle_callback
from skywalker.ui.output import OutputRenderer
from skywalker.ui.tool_panel import ToolPanel
from skywalker.ui.list_browser import ListBrowser, ListItem
from skywalker.session.tool_log import ToolLog

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


def _init_tools(
    project_root: str,
    confirm_callback=None,
) -> tuple[ToolRegistry, ToolExecutor]:
    """初始化工具系统"""
    registry = ToolRegistry()
    registry.register(FileTool())
    registry.register(ShellTool())
    registry.register(WebTool())

    sandbox = GitWorkTree(project_root) if settings.sandbox_enabled else None
    executor = ToolExecutor(sandbox=sandbox, confirm_callback=confirm_callback)
    return registry, executor

def _init_session(memory_manager, console):
    """初始化会话系统 和 命令系统"""
    store = SessionStore()
    session_manager = SessionManager(store, memory_manager)
    registry = CommandRegistry()
    register_builtin_commands(registry, session_manager, memory_manager, console)

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

    # 初始化渲染器和工具子界面
    renderer = OutputRenderer(style="default")
    tool_panel = ToolPanel(console=renderer.console)
    renderer.set_tool_panel(tool_panel)

    renderer.console.print("[bold orange1]Skywalker Agent[/] - 按下 'Ctrl+Z' 退出，'Ctrl+O' 查看工具历史\n")

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

    # 定义确认回调：停止所有渲染，请求用户确认
    def ask_user_confirm(cmd: str) -> bool:
        import sys
        renderer._stop_spinner()
        # 暂停 ToolPanel，保存状态
        tool_panel.pause()
        # 强制刷新输出
        sys.stdout.flush()
        sys.stderr.flush()
        renderer.console.print()
        renderer.console.print(f"[bold red]⚠️  Agent 想要运行:[/] {cmd}")
        renderer.console.print("[dim]输入 y 并按回车确认，其他键拒绝[/]")
        try:
            confirm = input("> ").strip().lower()
            # 恢复 ToolPanel，从保存的状态继续
            tool_panel.resume()
            return confirm == "y"
        except (EOFError, KeyboardInterrupt):
            tool_panel.resume()
            return False

    # 初始化工具
    registry, executor = _init_tools(project_root, confirm_callback=ask_user_confirm)

    # 构建带记忆和工具的系统提示
    system_prompt = _build_system_prompt(memory_manager, registry)

    # 初始化会话状态和命令系统
    store, session_manager, command_registry = _init_session(memory_manager, renderer.console)

    # 新建会话
    session_id = session_manager.new_session(project_root)
    renderer.console.print(f"[dim]已创建会话 {session_id}[/]\n")

    # 初始化工具日志
    session_dir = store._base_dir / session_id
    tool_log = ToolLog(session_dir=session_dir)
    renderer.set_tool_log(tool_log)

    # 设置 Ctrl+O 回调：打开工具历史浏览器
    def open_tool_browser():
        records = tool_log.get_all()
        if not records:
            renderer.console.print("[dim]暂无工具调用记录[/]")
            return

        items = [ListItem.from_tool_record(r) for r in records]
        browser = ListBrowser(console=renderer.console)
        browser.run(items, title="工具调用记录")

    set_toggle_callback(open_tool_browser)

    state = AgentState(project_root=project_root)
    turn_index = 0

    while True:
        user_input = await read_line(HTML("<ansiblue><b>You:</b></ansiblue> "))
        saved = None
        if user_input is None:
            # Ctrl+Z 退出：保存会话 + 记忆
            await session_manager.save_session()
            # saved = await memory_manager.on_shutdown(state)
            if saved:
                print("已退出，会话和记忆已保存！(跳过保存到MEMORY.md被跳过)")
            else:
                print("已退出，会话已保存。")
            break

        if user_input.strip().lower() == "exit":
            # exit 退出：保存会话 + 记忆
            await session_manager.save_session()
            # saved = await memory_manager.on_shutdown(state)
            if saved:
                print("会话和记忆已保存！(保存到MEMORY.md被跳过)")
            else:
                print("会话已保存。")
            break

        if user_input.strip().startswith("/"):
            # /exit 直接走退出流程
            if user_input.strip() == "/exit":
                await session_manager.save_session()
                # saved = await memory_manager.on_shutdown(state)
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
        turn_index += 1

        # 运行 loop（内部处理 LLM 调用、工具执行、压缩检查）
        state = await run_loop(
            state, llm, user_input,
            conv_manager=conv_manager,
            memory_manager=memory_manager,
            system_prompt=system_prompt,
            registry=registry,
            executor=executor,
            on_event=renderer.render_event,  # 事件回调
            tool_log=tool_log,               # 工具日志
            turn_index=turn_index,           # 当前轮次
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
