"""可选依赖管理 — 包名映射、检查、自动安装。"""
import logging
import os
import subprocess

logger = logging.getLogger("dep_utils")

# pkg_name -> (import_name, description)
OPTIONAL_DEPS = {
    "python-binance": ("binance", "Binance 加密货币数据源"),
    "yfinance": ("yfinance", "Yahoo Finance 多市场数据源"),
    "akshare": ("akshare", "AkShare A股/期货/外汇数据源"),
    "tushare": ("tushare", "Tushare A股数据源"),
    "mootdx": ("mootdx", "Mootdx 分钟线数据源"),
    "tqsdk": ("tqsdk", "天勤量化全市场数据源"),
}


def check_dep(pkg_name: str) -> dict:
    """检查单个依赖包的安装状态。"""
    info = OPTIONAL_DEPS.get(pkg_name, ("", ""))
    import_name, desc = info[0], info[1]
    installed = False
    try:
        __import__(import_name)
        installed = True
    except ImportError:
        pass
    return {
        "package": pkg_name,
        "import_name": import_name,
        "description": desc,
        "installed": installed,
    }


def auto_install_dep(pkg_name: str) -> bool:
    """尝试自动安装缺失的可选依赖包（使用当前 Python 解释器的 pip）。"""
    import sys
    try:
        logger.info("[自动安装] 正在安装 %s ...", pkg_name)
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", pkg_name, "-q"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=180,
        )
        logger.info("[自动安装] %s 安装成功", pkg_name)
        return True
    except Exception as e:
        logger.warning("[自动安装] %s 安装失败: %s", pkg_name, e)
        return False


def check_all_deps() -> tuple[list, list]:
    """检查所有可选依赖，返回 (已安装列表, 缺失列表)。"""
    auto_install = os.environ.get("AUTO_INSTALL_DEPS", "true").strip().lower() in ("true", "1", "yes")
    missing = []
    installed_new = []

    for pkg_name, (import_name, desc) in OPTIONAL_DEPS.items():
        try:
            __import__(import_name)
        except ImportError:
            if auto_install:
                if auto_install_dep(pkg_name):
                    installed_new.append(pkg_name)
                else:
                    missing.append(f"  - {pkg_name}（用于 {desc}）")
            else:
                missing.append(f"  - {pkg_name}（用于 {desc}）")

    return installed_new, missing
