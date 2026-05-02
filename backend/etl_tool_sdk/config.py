"""
SDK 全局配置 — 合规设计：仅工具自身配置，无第三方数据源信息。
"""
import os
from pathlib import Path
from typing import Optional


class SDKConfig:
    """SDK 全局配置类。"""

    # 默认数据目录（与工具主程序共享）
    DEFAULT_DATA_DIR = Path.home() / "JinZhiHuiETL"

    # 日志配置
    LOG_LEVEL = os.environ.get("JINZHIHUI_SDK_LOG_LEVEL", "INFO")
    LOG_DIR = DEFAULT_DATA_DIR / "logs"
    LOG_FILE = LOG_DIR / "sdk.log"
    LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT = 5

    # 数据库配置
    DB_PATH = DEFAULT_DATA_DIR / "jinzhihui.db"

    # HTTP 请求默认超时（秒）
    HTTP_TIMEOUT = 30

    # 脚本执行沙箱配置
    SANDBOX_ALLOW_NAMED_EXPRESSIONS = False
    SANDBOX_TIMEOUT_SECONDS = 300

    # 数据处理默认配置
    CHUNK_SIZE = 10000
    MAX_ROWS_IN_MEMORY = 1000000

    _initialized = False

    @classmethod
    def init(cls, data_dir: Optional[Path] = None, log_level: str = "INFO"):
        """初始化 SDK 配置。可在导入 SDK 前调用以覆盖默认值。

        Args:
            data_dir: 数据目录路径（默认 ~/.JinZhiHuiETL）
            log_level: 日志级别（DEBUG/INFO/WARNING/ERROR）
        """
        if data_dir:
            cls.DEFAULT_DATA_DIR = Path(data_dir)
            cls.LOG_DIR = cls.DEFAULT_DATA_DIR / "logs"
            cls.DB_PATH = cls.DEFAULT_DATA_DIR / "jinzhihui.db"

        cls.LOG_LEVEL = log_level.upper()
        cls._initialized = True

    @classmethod
    def ensure_dirs(cls):
        """确保必要目录存在。"""
        cls.LOG_DIR.mkdir(parents=True, exist_ok=True)


def init_sdk(data_dir: Optional[str] = None, log_level: str = "INFO") -> SDKConfig:
    """便捷初始化函数。

    Args:
        data_dir: 数据目录路径（字符串）
        log_level: 日志级别
    Returns:
        SDKConfig 实例
    """
    if data_dir:
        SDKConfig.init(Path(data_dir), log_level)
    else:
        SDKConfig.init(log_level=log_level)
    SDKConfig.ensure_dirs()
    return SDKConfig
