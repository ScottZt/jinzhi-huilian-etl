"""金智汇连ETL 后端启动入口 — PyInstaller 打包专用。

本文件为 PyInstaller 打包入口，不依赖任何 GUI/Tkinter 组件。
Electron 启动时会 spawn 此 exe，然后 BrowserWindow 访问其服务。"""
import os
import sys
import logging
import socket
import time
import traceback
import threading
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


# 启动自检日志器（在 main 里初始化后可用）。
_startup_logger = None


def _mask_secret(value: str) -> str:
    """脱敏敏感值，避免日志中泄露密钥明文。"""
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]


def _collect_env_summary() -> dict:
    """收集启动诊断所需的关键环境变量摘要（不记录敏感明文）。"""
    demo_key = os.environ.get("QS_ETL_DEMO_API_KEY", "")
    return {
        "JINZHIHUILIAN_PORT": os.environ.get("JINZHIHUILIAN_PORT", ""),
        "JINZHIHUI_PORT": os.environ.get("JINZHIHUI_PORT", ""),
        "QS_CLOUD_DEMO_MAX_CALLS": os.environ.get("QS_CLOUD_DEMO_MAX_CALLS", ""),
        "QS_SILICONFLOW_INVITE_URL": os.environ.get("QS_SILICONFLOW_INVITE_URL", ""),
        # 仅记录是否存在和脱敏摘要，避免密钥泄漏。
        "QS_ETL_DEMO_API_KEY_set": bool(demo_key.strip()),
        "QS_ETL_DEMO_API_KEY_masked": _mask_secret(demo_key.strip()),
    }


def _setup_startup_logger(data_dir: Path) -> logging.Logger:
    """创建启动自检文件日志，便于黑屏/启动失败快速定位。"""
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "startup_selfcheck.log"
    startup_logger = logging.getLogger("startup_selfcheck")
    startup_logger.setLevel(logging.INFO)
    startup_logger.propagate = False
    # 避免重复添加 handler（例如热重启或二次调用）。
    if not startup_logger.handlers:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        startup_logger.addHandler(file_handler)
    startup_logger.info("========== Startup Begin ==========")
    startup_logger.info("python=%s", sys.version.replace("\n", " "))
    startup_logger.info("platform=%s", sys.platform)
    startup_logger.info("frozen=%s", bool(getattr(sys, "frozen", False)))
    startup_logger.info("cwd=%s", os.getcwd())
    startup_logger.info("exe=%s", sys.executable)
    startup_logger.info("env=%s", _collect_env_summary())
    startup_logger.info("log_file=%s", str(log_file))
    return startup_logger


def _diag_info(message: str, *args):
    """统一写入自检日志与标准日志。"""
    if _startup_logger:
        _startup_logger.info(message, *args)
    logger.info(message, *args)


def _diag_exception(message: str, exc: BaseException):
    """统一记录异常详情（含 traceback）。"""
    err_text = f"{message}: {exc}"
    if _startup_logger:
        _startup_logger.error(err_text)
        _startup_logger.error(traceback.format_exc())
    logger.exception(err_text)


def _resource_path(relative: str) -> str:
    """Get absolute path to resource, works for dev and PyInstaller."""
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
        return str(base / relative)
    else:
        return str(Path(__file__).parent / relative)


def _is_port_in_use(port: int, host: str = '127.0.0.1') -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


def _find_free_port(start: int = 8080, end: int = 8099) -> int:
    for p in range(start, end + 1):
        if not _is_port_in_use(p):
            return p
    raise RuntimeError(f"No free port in range {start}-{end}")


def main():
    t0 = time.time()

    # 数据目录：frozen 时用 exe 同目录，否则用项目 backend 同级
    if getattr(sys, 'frozen', False):
        data_dir = Path(sys._MEIPASS) / 'data'
        backend_dir = Path(sys._MEIPASS)
    else:
        backend_dir = Path(__file__).parent
        data_dir = backend_dir.parent / 'data'

    data_dir.mkdir(parents=True, exist_ok=True)
    global _startup_logger
    _startup_logger = _setup_startup_logger(data_dir)
    os.environ['JINZHIHUILIAN_DATA_DIR'] = str(data_dir)
    os.environ['JINZHIHUI_DATA_DIR'] = str(data_dir)
    _diag_info("[BOOT] data_dir=%s", str(data_dir))

    # 捕获未处理异常，确保黑屏场景也能落盘日志。
    def _on_unhandled_exception(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        if _startup_logger:
            _startup_logger.error("[UNHANDLED] %s", text)
        logger.error("[UNHANDLED] %s", text)
    sys.excepthook = _on_unhandled_exception

    # 捕获子线程未处理异常（Python 3.8+）。
    def _on_thread_exception(args):
        if _startup_logger:
            _startup_logger.error("[THREAD-UNHANDLED] thread=%s exc=%s", args.thread.name, args.exc_value)
            _startup_logger.error("".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
        logger.error("[THREAD-UNHANDLED] thread=%s exc=%s", args.thread.name, args.exc_value)
    threading.excepthook = _on_thread_exception

    _diag_info("[BOOT] Starting 金智汇连ETL backend (t=0s)")

    # 端口检测 — 复用已有后端
    try:
        port = _find_free_port(8080, 8099)
    except Exception as e:
        _diag_exception("[BOOT] Find free port failed", e)
        raise
    if port != 8080:
        _diag_info("[BOOT] Port 8080 in use, using %s", port)
    else:
        _diag_info("[BOOT] Using default port %s", port)

    # 将 backend 目录加入 sys.path 以便后续 import
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    _diag_info("[BOOT] backend_dir=%s", str(backend_dir))

    # 初始化数据库
    try:
        _diag_info("[BOOT] Init DB (t=%.1fs)", time.time() - t0)
        from app.persistence.sqlite_repo import init_db
        init_db()
    except Exception as e:
        _diag_exception("[BOOT] Init DB failed", e)
        raise

    # 初始化调度器
    try:
        _diag_info("[BOOT] Init scheduler (t=%.1fs)", time.time() - t0)
        from app.core.task_scheduler import init_scheduler
        init_scheduler()
    except Exception as e:
        _diag_exception("[BOOT] Init scheduler failed", e)
        raise

    # 导入 FastAPI app
    try:
        _diag_info("[BOOT] Import app.main (t=%.1fs)", time.time() - t0)
        from app.main import app
    except Exception as e:
        _diag_exception("[BOOT] Import app.main failed", e)
        raise

    # 启动 uvicorn
    try:
        import uvicorn
        _diag_info("[BOOT] Uvicorn starting host=127.0.0.1 port=%s", port)
        uvicorn.run(
            app,
            host='127.0.0.1',
            port=port,
            log_level='info',
            access_log=False,
        )
    except Exception as e:
        _diag_exception("[BOOT] Uvicorn failed", e)
        raise


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        # 兜底输出日志路径，方便用户第一时间定位。
        data_dir_hint = os.environ.get("JINZHIHUILIAN_DATA_DIR", "")
        if data_dir_hint:
            print(f"[FATAL] 启动失败，请查看日志：{data_dir_hint}\\logs\\startup_selfcheck.log", file=sys.stderr)
        else:
            print("[FATAL] 启动失败，请查看 stderr 日志输出。", file=sys.stderr)
        raise
