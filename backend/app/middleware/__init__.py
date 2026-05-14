"""API 限流中间件 — 基于内存的简单令牌桶，单 IP 限频。"""
import time
from collections import defaultdict
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """按 IP 限制请求频率，默认 100 次/分钟。"""

    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # {ip: [(timestamp, ...)]}
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def _cleanup(self, ip: str, now: float):
        cutoff = now - self.window_seconds
        self._buckets[ip] = [t for t in self._buckets[ip] if t > cutoff]

    async def dispatch(self, request: Request, call_next):
        # 跳过静态资源和健康检查
        path = request.url.path
        if (path.startswith("/static")
                or path.startswith("/favicon")
                or path == "/health"
                or path.startswith("/docs")
                or path.startswith("/openapi.json")):
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        now = time.time()
        self._cleanup(ip, now)

        if len(self._buckets[ip]) >= self.max_requests:
            return Response(
                content=f"请求过于频繁，请稍后重试 ({self.max_requests}次/{self.window_seconds}秒)",
                status_code=429,
                media_type="text/plain; charset=utf-8",
                headers={"Retry-After": str(self.window_seconds)},
            )

        self._buckets[ip].append(now)
        return await call_next(request)
