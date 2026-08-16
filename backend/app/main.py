from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
import json
import os
import sys
import logging
import time as _main_time
from pathlib import Path
import asyncio

_t = _main_time.time
logger = logging.getLogger(__name__)
logger.info(f"[BOOT] main.py import start (t=0)")

from app.api import connections; logger.info(f"[BOOT] app.api.connections loaded (t={_t():.1f}s)")
from app.api import schemas; logger.info(f"[BOOT] app.api.schemas loaded (t={_t():.1f}s)")
from app.api import auth; logger.info(f"[BOOT] app.api.auth loaded (t={_t():.1f}s)")
from app.api import tasks; logger.info(f"[BOOT] app.api.tasks loaded (t={_t():.1f}s)")
from app.api import bulk_import; logger.info(f"[BOOT] app.api.bulk_import loaded (t={_t():.1f}s)")
from app.api import monitor; logger.info(f"[BOOT] app.api.monitor loaded (t={_t():.1f}s)")
from app.api import file_watchers; logger.info(f"[BOOT] app.api.file_watchers loaded (t={_t():.1f}s)")
from app.api import transforms; logger.info(f"[BOOT] app.api.transforms loaded (t={_t():.1f}s)")
from app.api import reports; logger.info(f"[BOOT] app.api.reports loaded (t={_t():.1f}s)")
from app.api import kline_sources; logger.info(f"[BOOT] app.api.kline_sources loaded (t={_t():.1f}s)")
from app.api import credentials; logger.info(f"[BOOT] app.api.credentials loaded (t={_t():.1f}s)")
from app.api import kline_sync_tasks; logger.info(f"[BOOT] app.api.kline_sync_tasks loaded (t={_t():.1f}s)")
from app.api import workflows; logger.info(f"[BOOT] app.api.workflows loaded (t={_t():.1f}s)")
from app.api import pipelines; logger.info(f"[BOOT] app.api.pipelines loaded (t={_t():.1f}s)")
from app.api import license; logger.info(f"[BOOT] app.api.license loaded (t={_t():.1f}s)")
from app.api import ai_script; logger.info(f"[BOOT] app.api.ai_script loaded (t={_t():.1f}s)")
from app.api import llm; logger.info(f"[BOOT] app.api.llm loaded (t={_t():.1f}s)")
from app.api import file_utils; logger.info(f"[BOOT] app.api.file_utils loaded (t={_t():.1f}s)")
from app.api import contracts; logger.info(f"[BOOT] app.api.contracts loaded (t={_t():.1f}s)")
from app.api import deps; logger.info(f"[BOOT] app.api.deps loaded (t={_t():.1f}s)")
from app.api import adj_factors; logger.info(f"[BOOT] app.api.adj_factors loaded (t={_t():.1f}s)")
from app.api import factors; logger.info(f"[BOOT] app.api.factors loaded (t={_t():.1f}s)")
from app.api import content_packs; logger.info(f"[BOOT] app.api.content_packs loaded (t={_t():.1f}s)")
from app.core.websocket_manager import get_ws_manager; logger.info(f"[BOOT] websocket_manager loaded (t={_t():.1f}s)")
from app.persistence.sqlite_repo import init_db; logger.info(f"[BOOT] sqlite_repo.init_db loaded (t={_t():.1f}s)")
logger.info(f"[BOOT] All imports done")


from app.config import DEFAULT_PORT, PORT_RANGE, resource_path, find_free_port; logger.info(f"[BOOT] app.config loaded (t={_t():.1f}s)")

def _resource_path(relative: str) -> str:
    """Get absolute path to resource, works for dev and PyInstaller."""
    return resource_path(relative)


# Prefer unified env naming for port, keep legacy env naming fallback.
# Port range is defined in app.config (DEFAULT_PORT, PORT_RANGE).

# Note: init_db() and init_audit_db() are handled in lifespan().

_broadcast_task = None

from app.dep_utils import OPTIONAL_DEPS, check_all_deps


def _check_optional_deps():
    """启动时检查可选依赖包，缺失时自动安装或给出安装提示。"""
    import logging
    _logger = logging.getLogger(__name__)
    installed_new, missing = check_all_deps()
    if installed_new:
        _logger.info("[启动检查] 已自动安装: %s", ", ".join(installed_new))
    if missing:
        _logger.warning(
            "[启动检查] 以下可选依赖未安装，对应数据源将不可用:\n%s\n"
            "可通过以下命令安装:\n  pip install %s\n"
            "或设置环境变量 AUTO_INSTALL_DEPS=true 启用自动安装",
            "\n".join(missing),
            " ".join(m[2:].split("（")[0].strip().replace("- ", "") for m in missing),
        )


async def _periodic_broadcast():
    """Periodically broadcast status to all WebSocket clients."""
    manager = get_ws_manager()
    while True:
        await asyncio.sleep(5)
        if manager._connections:
            await manager.broadcast_status()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _broadcast_task
    # Ensure schema exists for standalone startup path.
    init_db()
    _init_audit_db()
    _check_optional_deps()

    # 启动定时任务调度器，恢复 tasks 和 pipelines 的定时任务
    from app.core.task_scheduler import init_scheduler
    init_scheduler()
    logger.info("[BOOT] Task scheduler initialized")

    # Pre-generate API key and log path for Electron/frontend
    api_key_path = get_api_key_path()
    api_key = get_or_create_api_key()
    logger.info(f"[AUTH] API key stored at: {api_key_path}")
    _broadcast_task = asyncio.create_task(_periodic_broadcast())
    yield
    if _broadcast_task:
        _broadcast_task.cancel()
        try:
            await _broadcast_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="金智汇联ETL", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1", "http://localhost"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)

# API 限流中间件（500 次/分钟/IP）
from app.middleware import RateLimiterMiddleware
app.add_middleware(RateLimiterMiddleware, max_requests=500, window_seconds=60)

# API 审计日志中间件
from app.middleware.api_audit import ApiAuditMiddleware, _init_audit_db
app.add_middleware(ApiAuditMiddleware)

# API 鉴权中间件
from app.middleware.auth import ApiAuthMiddleware, get_or_create_api_key, get_api_key_path
app.add_middleware(ApiAuthMiddleware)


# 静态 HTML 文件 no-cache 中间件 — 确保浏览器始终获取最新版本
class StaticNoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.endswith(".html") or path.endswith(".js"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response


app.add_middleware(StaticNoCacheMiddleware)

app.include_router(connections.router, prefix="/api/connections", tags=["connections"])
app.include_router(schemas.router, prefix="/api/schemas", tags=["schemas"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(bulk_import.router, prefix="/api/bulk-import", tags=["bulk-import"])
app.include_router(monitor.router, prefix="/api/monitor", tags=["monitor"])
app.include_router(file_watchers.router, prefix="/api/file-watchers", tags=["file-watchers"])
app.include_router(transforms.router, prefix="/api/transforms", tags=["transforms"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(kline_sources.router, prefix="/api/kline-sources", tags=["kline-sources"])
app.include_router(credentials.router, prefix="/api/credentials", tags=["credentials"])
app.include_router(kline_sync_tasks.router, prefix="/api/kline-sync-tasks", tags=["kline-sync-tasks"])
app.include_router(workflows.router, prefix="/api/workflows", tags=["workflows"])
app.include_router(pipelines.router, prefix="/api/pipelines", tags=["pipelines"])
app.include_router(license.router, prefix="/api/license", tags=["license"])
app.include_router(ai_script.router, prefix="/api/ai-script", tags=["ai-script"])
app.include_router(llm.router, prefix="/api/llm", tags=["llm"])
app.include_router(file_utils.router, prefix="/api/files", tags=["files"])
app.include_router(contracts.router, prefix="/api/contracts", tags=["contracts"])
app.include_router(deps.router, prefix="/api/deps", tags=["deps"])
app.include_router(adj_factors.router, prefix="/api/adj-factors", tags=["adj-factors"])
app.include_router(factors.router, prefix="/api/factors", tags=["factors"])
app.include_router(content_packs.router, prefix="/api/content-packs", tags=["content-packs"])

static_dir = _resource_path("static")

# HTML 文件使用 no-cache 确保浏览器始终获取最新版本
_NO_CACHE_HEADERS = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}


@app.get("/static/workflow-editor.html")
async def workflow_editor_static():
    return FileResponse(f"{static_dir}/workflow-editor.html", headers=_NO_CACHE_HEADERS)


@app.get("/static/index.html")
async def index_html_static():
    return FileResponse(f"{static_dir}/index.html", headers=_NO_CACHE_HEADERS)


@app.get("/adj-factors")
async def adj_factors_page():
    """复权因子查询页面"""
    return FileResponse(f"{static_dir}/adj-factors.html", headers=_NO_CACHE_HEADERS)


app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    return FileResponse(_resource_path("static/index.html"), headers=_NO_CACHE_HEADERS)


@app.get("/workflow-editor.html")
async def workflow_editor():
    return FileResponse(_resource_path("static/workflow-editor.html"), headers=_NO_CACHE_HEADERS)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    manager = get_ws_manager()
    await manager.connect(websocket)
    try:
        await manager.broadcast_status()
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

