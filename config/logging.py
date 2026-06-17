import logging
import logging.config
from pathlib import Path


def setup_logging(log_dir: str = "logs", debug: bool = False):
    Path(log_dir).mkdir(exist_ok=True)

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "detailed": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
            },
            "simple": {
                "format": "%(asctime)s | %(levelname)-8s | %(message)s"
            },
        },
        "handlers": {
            "skywalker_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": f"{log_dir}/skywalker.log",
                "maxBytes": 5_000_000,   # 5MB 自动轮转
                "backupCount": 3,
                "formatter": "simple",
                "level": "WARNING",
            },
            "agent_file": {
                "class": "logging.FileHandler",
                "filename": f"{log_dir}/agent.log",
                "formatter": "detailed",
                "level": "DEBUG",
            },
            "memory_file": {
                "class": "logging.FileHandler",
                "filename": f"{log_dir}/memory.log",
                "formatter": "detailed",
                "level": "DEBUG",
            },
            "tools_file": {
                "class": "logging.FileHandler",
                "filename": f"{log_dir}/tools.log",
                "formatter": "detailed",
                "level": "DEBUG",
            },
            "debug_file": {
                "class": "logging.FileHandler",
                "filename": f"{log_dir}/debug.log",
                "formatter": "detailed",
                "level": "DEBUG",
            },
        },
        "loggers": {
            "skywalker": {
                "handlers": ["skywalker_file"],
                "level": "WARNING",
                "propagate": False,
            },
            "skywalker.agent": {
                "handlers": ["agent_file", "debug_file"],
                "level": "DEBUG",
                "propagate": True,
            },
            "skywalker.memory": {
                "handlers": ["memory_file", "debug_file"],
                "level": "DEBUG",
                "propagate": True,
            },
            "skywalker.tools": {
                "handlers": ["tools_file", "debug_file"],
                "level": "DEBUG",
                "propagate": True,
            },
            "skywalker.llm": {
                "handlers": ["debug_file"],
                "level": "DEBUG",
                "propagate": True,
            },
            "skywalker.session": {
                "handlers": ["debug_file"],
                "level": "DEBUG",
                "propagate": True,
            },
        },
    }

    # 生产环境关闭 debug.log
    if not debug:
        del config["handlers"]["debug_file"]
        for logger_config in config["loggers"].values():
            if "debug_file" in logger_config["handlers"]:
                logger_config["handlers"].remove("debug_file")

    logging.config.dictConfig(config)