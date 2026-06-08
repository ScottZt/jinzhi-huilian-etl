"""API 鉴权中间件 — 基于本地 API Key 的简单鉴权。

桌面端场景：
  - 首次启动时自动生成 API Key，保存到本地文件
  - 所有 /api/* 请求必须携带 X-API-Key 请求头
  - 健康检查、静态资源、WebSocket 不需要鉴权
  - 前端 Electron 进程从本地文件读取 API Key 并自动附加
"""
import os
import secrets
from pathlib import Path
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

_API_KEY_FILE: Optional[Path] = None
_cached_api_key: Optional[str] = None

# Paths that don't require authentication
_PUBLIC_PATHS = frozenset({
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/auth/key",  # Public endpoint for frontend to get API key (localhost only)
})


def _get_data_dir() -> Path:
    if os.environ.get("JINZHIHUILIAN_DATA_DIR"):
        return Path(os.environ["JINZHIHUILIAN_DATA_DIR"])
    elif os.environ.get("JINZHIHUI_DATA_DIR"):
        return Path(os.environ["JINZHIHUI_DATA_DIR"])
    elif os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "jinzhihuilian"
    else:
        return Path(__file__).parent.parent.parent.parent / "shared"


def get_api_key_path() -> Path:
    global _API_KEY_FILE
    if _API_KEY_FILE is not None:
        return _API_KEY_FILE
    data_dir = _get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    _API_KEY_FILE = data_dir / ".api_key"
    return _API_KEY_FILE


def get_or_create_api_key() -> str:
    """读取或生成 API Key。首次启动时生成并保存到文件。"""
    global _cached_api_key
    if _cached_api_key is not None:
        return _cached_api_key

    key_path = get_api_key_path()
    if key_path.exists():
        _cached_api_key = key_path.read_text().strip()
        return _cached_api_key

    # Generate a new API key
    _cached_api_key = secrets.token_urlsafe(32)
    key_path.write_text(_cached_api_key)
    try:
        os.chmod(key_path, 0o600)
    except Exception:
        pass
    return _cached_api_key


class ApiAuthMiddleware(BaseHTTPMiddleware):
    """Require X-API-Key header for all /api/* endpoints."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip public paths
        if path in _PUBLIC_PATHS or path.startswith("/static") or path.startswith("/favicon"):
            return await call_next(request)

        # Skip WebSocket
        if path.startswith("/ws"):
            return await call_next(request)

        # Only protect /api/* paths
        if not path.startswith("/api/"):
            return await call_next(request)

        # Check API key
        api_key = request.headers.get("X-API-Key", "")
        if not api_key:
            # Also check query parameter for browser-based access
            api_key = request.query_params.get("api_key", "")

        valid_key = get_or_create_api_key()
        if api_key != valid_key:
            return Response(
                content="鉴权失败：请在请求头中携带 X-API-Key",
                status_code=401,
                media_type="text/plain; charset=utf-8",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        return await call_next(request)
