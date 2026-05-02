"""
日志记录接口 — 合规设计：封装工具自身日志能力，不涉及任何第三方数据源。
"""
import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from logging.handlers import RotatingFileHandler

from etl_tool_sdk.config import SDKConfig


class LogHandler:
    """
    日志处理器 — 提供结构化日志记录能力，支持文件和控制台输出。

    合规说明：仅记录工具自身运行日志，不存储任何第三方数据源信息。
    日志内容由用户自行审核，涉及数据源的信息由用户自行脱敏。

    使用示例：
        LogHandler.info("ETL 流程开始", extra={"task_id": "sync_001"})

        LogHandler.error("数据写入失败", extra={
            "error": str(e),
            "rows_affected": 0,
        })

        # 获取专用 logger
        logger = LogHandler.get_logger("my_module")
        logger.warning("这是一条自定义日志")
    """

    _loggers: Dict[str, logging.Logger] = {}
    _initialized = False

    @classmethod
    def _ensure_init(cls):
        """确保日志系统已初始化。"""
        if cls._initialized:
            return

        SDKConfig.ensure_dirs()

        log_file = str(SDKConfig.LOG_DIR / "sdk.log")
        level = getattr(logging, SDKConfig.LOG_LEVEL.upper(), logging.INFO)

        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        root_logger = logging.getLogger("etl_tool_sdk")
        root_logger.setLevel(level)

        if not root_logger.handlers:
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=SDKConfig.LOG_MAX_BYTES,
                backupCount=SDKConfig.LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)

            console_handler = logging.StreamHandler()
            console_handler.setLevel(level)
            console_handler.setFormatter(formatter)
            root_logger.addHandler(console_handler)

        cls._initialized = True

    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """获取指定名称的 logger。"""
        cls._ensure_init()
        if name not in cls._loggers:
            cls._loggers[name] = logging.getLogger(f"etl_tool_sdk.{name}")
        return cls._loggers[name]

    @classmethod
    def info(cls, message: str, extra: Optional[Dict[str, Any]] = None):
        """记录 INFO 日志。"""
        cls._ensure_init()
        logger = logging.getLogger("etl_tool_sdk")
        if extra:
            extra_str = " | ".join(f"{k}={v}" for k, v in extra.items())
            logger.info(f"{message} [{extra_str}]")
        else:
            logger.info(message)

    @classmethod
    def warning(cls, message: str, extra: Optional[Dict[str, Any]] = None):
        """记录 WARNING 日志。"""
        cls._ensure_init()
        logger = logging.getLogger("etl_tool_sdk")
        if extra:
            extra_str = " | ".join(f"{k}={v}" for k, v in extra.items())
            logger.warning(f"{message} [{extra_str}]")
        else:
            logger.warning(message)

    @classmethod
    def error(cls, message: str, extra: Optional[Dict[str, Any]] = None):
        """记录 ERROR 日志。"""
        cls._ensure_init()
        logger = logging.getLogger("etl_tool_sdk")
        if extra:
            extra_str = " | ".join(f"{k}={v}" for k, v in extra.items())
            logger.error(f"{message} [{extra_str}]")
        else:
            logger.error(message)

    @classmethod
    def debug(cls, message: str, extra: Optional[Dict[str, Any]] = None):
        """记录 DEBUG 日志。"""
        cls._ensure_init()
        logger = logging.getLogger("etl_tool_sdk")
        if extra:
            extra_str = " | ".join(f"{k}={v}" for k, v in extra.items())
            logger.debug(f"{message} [{extra_str}]")
        else:
            logger.debug(message)

    @classmethod
    def log_run(
        cls,
        task_id: str,
        status: str,
        rows: int = 0,
        duration_seconds: float = 0,
        error: Optional[str] = None,
    ):
        """记录任务执行日志（结构化）。"""
        cls._ensure_init()
        logger = logging.getLogger("etl_tool_sdk.task")
        entry = {
            "task_id": task_id,
            "status": status,
            "rows": rows,
            "duration_s": round(duration_seconds, 2),
            "ts": datetime.now().isoformat(),
        }
        if error:
            entry["error"] = error
        logger.info(f"Task run: {task_id} | {status} | rows={rows} | duration={duration_seconds:.2f}s")

    @classmethod
    def get_recent_logs(
        cls,
        lines: int = 100,
        level: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> list:
        """
        获取最近日志。

        Args:
            lines: 返回行数上限
            level: 过滤级别（DEBUG/INFO/WARNING/ERROR）
            task_id: 过滤任务 ID
        Returns:
            日志行列表
        """
        cls._ensure_init()
        log_file = SDKConfig.LOG_DIR / "sdk.log"
        if not log_file.exists():
            return []

        result = []
        try:
            with open(log_file, encoding="utf-8") as f:
                for line in f:
                    if level and f"[{level}]" not in line:
                        continue
                    if task_id and task_id not in line:
                        continue
                    result.append(line.strip())
        except Exception:
            return []

        return result[-lines:]

    @classmethod
    def clear_logs(cls):
        """清空日志文件。"""
        log_file = SDKConfig.LOG_DIR / "sdk.log"
        if log_file.exists():
            log_file.write_text("", encoding="utf-8")

    @classmethod
    def set_level(cls, level: str):
        """动态设置日志级别。"""
        lvl = getattr(logging, level.upper(), logging.INFO)
        logger = logging.getLogger("etl_tool_sdk")
        logger.setLevel(lvl)
        for handler in logger.handlers:
            handler.setLevel(lvl)
