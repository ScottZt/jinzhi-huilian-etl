from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
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
from app.core.websocket_manager import get_ws_manager; logger.info(f"[BOOT] websocket_manager loaded (t={_t():.1f}s)")
logger.info(f"[BOOT] All imports done")


def _resource_path(relative: str) -> str:
    """Get absolute path to resource, works for dev and PyInstaller."""
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
        candidate = base / "app" / relative
        if not candidate.exists():
            candidate = base / relative
        return str(candidate)
    else:
        base = Path(__file__).parent
    return str(base / relative)


DEFAULT_PORT = int(os.environ.get("JINZHIHUI_PORT", "8080"))
MAX_PORT = DEFAULT_PORT + 19

# Note: init_db(), init_scheduler() and port scanning are handled by tray_app.py
# No slow operations at import time.

_broadcast_task = None


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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(connections.router, prefix="/api/connections", tags=["connections"])
app.include_router(schemas.router, prefix="/api/schemas", tags=["schemas"])
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

static_dir = _resource_path("static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    return FileResponse(_resource_path("static/index.html"))


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

