from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv
load_dotenv()
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
    shell_deny_patterns: list[str] = field(default_factory=lambda: [
        "rm -rf /", "dd if=", "mkfs", ":(){ :|:& };:"
    ])
    # 需要用户确认的命令
    shell_ask_patterns: list[str] = field(default_factory=lambda: [
        "rm ", "mv ", "chmod ", "chown ", "sudo "
    ])

    # 会话配置
    session_auto_save: bool = True
    max_sessions: int = 10
    session_dir: str = "~/.skywalker/sessions"
    config_file: str = "~/.skywalker/config.yaml"

    def save(self) -> None:
        """将当前配置写入 config.yaml"""
        config_path = Path(os.path.expanduser(self.config_file))
        config_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "compressor_type": self.compressor_type,
            "memory_dir": self.memory_dir,
            "project_memory_file": self.project_memory_file,
            "compress_threshold": self.compress_threshold,
            "max_memory_entries": self.max_memory_entries,
            "context_window": self.context_window,
            "tool_timeout": self.tool_timeout,
            "shell_max_output_tokens": self.shell_max_output_tokens,
            "sandbox_enabled": self.sandbox_enabled,
            "sandbox_dir": self.sandbox_dir,
            "session_auto_save": self.session_auto_save,
            "max_sessions": self.max_sessions,
            "session_dir": self.session_dir,
            "config_file": self.config_file,
        }
        config_path.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False),
            encoding="utf-8"
        )
    
    @classmethod
    def load(cls) -> Settings:
        """从 config.yaml 加载配置,不存在返回默认值
            优先级: 环境变量 > config.yaml > 默认值
        """
        config_path = Path(os.path.expanduser("~/.skywalker/config.yaml"))
        settings = cls()

        if not config_path.exists():
            return settings
        try:
            data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return settings
        
            # 优先环境变量
            for key, value in data.items():
                if hasattr(settings, key):
                    # 环境变量存在,则跳过以保持环境变量优先
                    env_key =key.upper()
                    if env_key in os.environ:
                        continue
                    setattr(settings, key, value)
        except Exception:
            pass # 失败了,返回默认值
        return settings
# 全局设置实例
settings = Settings()