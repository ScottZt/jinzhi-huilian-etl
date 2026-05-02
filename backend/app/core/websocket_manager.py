"""
WebSocket manager for real-time status broadcasting.
"""
import asyncio
import json
import logging
from typing import Dict, Set, Any
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
import threading

from app.persistence import sqlite_repo

logger = logging.getLogger(__name__)


class WebSocketManager:

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._connections: Set[WebSocket] = set()
            cls._instance._lock = threading.Lock()
            cls._instance._broadcast_task: asyncio.Task = None
        return cls._instance

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        with self._lock:
            self._connections.add(websocket)
        logger.info(f"WebSocket connected. Total: {len(self._connections)}")

    def disconnect(self, websocket: WebSocket):
        with self._lock:
            self._connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self._connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast a message to all connected WebSocket clients."""
        if not self._connections:
            return

        payload = json.dumps(message, default=str)
        dead = set()

        with self._lock:
            connections = list(self._connections)

        for conn in connections:
            try:
                await conn.send_text(payload)
            except Exception:
                dead.add(conn)

        if dead:
            with self._lock:
                self._connections -= dead

    def broadcast_sync(self, message: Dict[str, Any]):
        """Thread-safe broadcast from sync context (e.g. import engine threads)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(self.broadcast(message), loop)
            else:
                asyncio.run(self.broadcast(message))
        except Exception as e:
            logger.warning(f"WebSocket broadcast failed: {e}")

    async def broadcast_status(self):
        """Broadcast current system status snapshot."""
        try:
            tasks = sqlite_repo.list_tasks()
            imports = sqlite_repo.list_bulk_imports()

            message = {
                "type": "status_update",
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "tasks": {
                        "total": len(tasks),
                        "running": sum(1 for t in tasks if t.get("status") == "running"),
                        "completed": sum(1 for t in tasks if t.get("status") == "completed"),
                        "failed": sum(1 for t in tasks if t.get("status") == "failed"),
                    },
                    "bulk_imports": {
                        "total": len(imports),
                        "running": sum(1 for i in imports if i.get("status") == "running"),
                        "total_rows_imported": sum(i.get("imported_rows", 0) for i in imports),
                    },
                },
            }
            await self.broadcast(message)
        except Exception as e:
            logger.warning(f"Status broadcast failed: {e}")

    async def broadcast_import_update(self, import_id: str, record: Dict[str, Any]):
        """Broadcast a specific import status update."""
        total = record.get("total_rows", 0) or 1
        imported = record.get("imported_rows", 0) or 0
        await self.broadcast({
            "type": "import_update",
            "timestamp": datetime.utcnow().isoformat(),
            "import_id": import_id,
            "status": record.get("status"),
            "progress_pct": round(imported / total * 100, 1),
            "imported_rows": imported,
            "total_rows": record.get("total_rows"),
        })

    async def broadcast_task_update(self, task_id: str, record: Dict[str, Any]):
        """Broadcast a specific task status update."""
        await self.broadcast({
            "type": "task_update",
            "timestamp": datetime.utcnow().isoformat(),
            "task_id": task_id,
            "status": record.get("status"),
            "last_run_at": record.get("last_run_at"),
        })

    async def broadcast_log(self, level: str, message: str):
        """Broadcast a log message."""
        await self.broadcast({
            "type": "log",
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message,
        })


_manager = WebSocketManager()


def get_ws_manager() -> WebSocketManager:
    return _manager
