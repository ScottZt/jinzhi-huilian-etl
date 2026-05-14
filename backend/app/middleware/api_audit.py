"""API 审计日志中间件 — 拦截 /api/* 请求，落库留存 30 天。"""
import time
import sqlite3
import threading
from pathlib import Path
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

_db_lock = threading.Lock()


def _get_db_path() -> Path:
    """返回审计日志数据库路径（与业务 SQLite 同目录）。"""
    from app.persistence import sqlite_repo
    return sqlite_repo.DB_PATH.parent / "api_audit.db"


def _init_audit_db():
    """确保审计表存在。"""
    db_path = _get_db_path()
    with _db_lock:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_audit_log (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp  TEXT    NOT NULL,
                    ip         TEXT    NOT NULL,
                    method     TEXT    NOT NULL,
                    path       TEXT    NOT NULL,
                    status     INTEGER NOT NULL,
                    latency_ms REAL   NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts ON api_audit_log(timestamp)")
            conn.commit()
        finally:
            conn.close()


def _write_audit_record(timestamp: str, ip: str, method: str, path: str, status: int, latency_ms: float):
    """写入一条审计记录。"""
    db_path = _get_db_path()
    with _db_lock:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "INSERT INTO api_audit_log (timestamp, ip, method, path, status, latency_ms) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (timestamp, ip, method, path, status, latency_ms),
            )
            conn.commit()
        finally:
            conn.close()


def cleanup_old_records(retention_days: int = 30):
    """清理超过保留天数的旧记录。"""
    db_path = _get_db_path()
    with _db_lock:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "DELETE FROM api_audit_log WHERE timestamp < datetime('now', ?)",
                (f"-{retention_days} days",),
            )
            conn.commit()
        finally:
            conn.close()


class ApiAuditMiddleware(BaseHTTPMiddleware):
    """拦截所有 /api/* 请求并记录审计日志。"""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api"):
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        method = request.method
        t0 = time.time()

        response = await call_next(request)

        latency_ms = (time.time() - t0) * 1000
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
        _write_audit_record(timestamp, ip, method, path, response.status_code, latency_ms)

        return response
