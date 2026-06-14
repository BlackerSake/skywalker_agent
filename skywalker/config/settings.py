from dataclasses import dataclass, field
import os

@dataclass
class Settings:
    """Skywalker 全局配置"""

    # LLM 配置
    model: str = os.environ["MODEL_ID"]
    max_tokens: int = 4096

    # 记忆系统配置
    compressor_type: str = "llm"           # "llm" | "subagent"（V5）
    memory_dir: str = "~/.skywalker"
    project_memory_file: str = "MEMORY.md"
    compress_threshold: float = 0.75       # token 使用率超过此值触发压缩
    max_memory_entries: int = 100          # 单文件最大条目数

    # 上下文配置
    context_window: int = 8000             # 模型上下文窗口大小

    # 项目配置
    project_root: str = "."

    # 工具执行配置
    tool_timeout: int = 30 
    shell_max_output_tokens: int = 5000
    sandbox_enabled: bool = True
    sandbox_dir: str = ".skywalker-sandbox"

    # 权限规则
    # 直接拒绝的shell
    shell_deny_patterns: list[str] = [
        "rm -rf /", "dd if=", "mkfs", ":(){ :|:& };:"
    ]
    # 需要用户确认的命令
    shell_ask_patterns: list[str] = [   
    "rm ", "mv ", "chmod ", "chown ", "sudo "
    ]

# 全局设置实例
settings = Settings()