from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Callable, Dict, Tuple

import anyio
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from openproject_mcp.transports.http.config import HttpConfig


def _hmac_digest(key: str, secret: str | None) -> str:
    if secret:
        return hmac.new(secret.encode(), key.encode(), hashlib.sha256).hexdigest()
    return hashlib.sha256(key.encode()).hexdigest()


def _log_hash(key: str, secret: str | None) -> str:
    digest = _hmac_digest(key, secret)
    return digest[:12]


@dataclass
class _Entry:
    window_start: int
    count: int
    last_seen_window: int
    last_used_seq: int


class _FixedWindowLimiter:
    def __init__(
        self,
        *,
        limit: int,
        window_s: int,
        max_keys: int,
        ttl_windows: int,
        hash_secret: str | None,
    ):
        self.limit = limit
        self.window_s = window_s
        self.max_keys = max_keys
        self.ttl_windows = ttl_windows
        self.hash_secret = hash_secret
        self._entries: Dict[str, _Entry] = {}
        self._seq = 0
        self._lock = anyio.Lock()

    def _digest(self, key: str) -> str:
        return _hmac_digest(key, self.hash_secret)

    async def check_and_increment(self, key: str, now: float) -> Tuple[bool, int, int]:
        """
        Returns (allowed, remaining, retry_after_seconds)
        retry_after_seconds meaningful only when not allowed.
        """
        async with self._lock:
            self._seq += 1
            seq = self._seq
            window_start = int(now // self.window_s) * self.window_s
            digest = self._digest(key)

            # TTL cleanup
            to_delete = []
            for k, entry in self._entries.items():
                if (
                    window_start - entry.last_seen_window
                ) // self.window_s >= self.ttl_windows:
                    to_delete.append(k)
            for k in to_delete:
                self._entries.pop(k, None)

            entry = self._entries.get(digest)
            if entry is None:
                # Evict if needed
                if len(self._entries) >= self.max_keys:
                    # Evict least recently used (smallest last_used_seq, tie by key)
                    victim = min(
                        self._entries.items(),
                        key=lambda item: (item[1].last_used_seq, item[0]),
                    )[0]
                    self._entries.pop(victim, None)
                entry = _Entry(
                    window_start=window_start,
                    count=0,
                    last_seen_window=window_start,
                    last_used_seq=seq,
                )
                self._entries[digest] = entry

            # New window?
            if entry.window_start != window_start:
                entry.window_start = window_start
                entry.count = 0

            entry.last_seen_window = window_start
            entry.last_used_seq = seq

            if entry.count >= self.limit:
                retry_after = (entry.window_start + self.window_s) - int(now)
                return False, 0, max(retry_after, 1)

            entry.count += 1
            remaining = max(self.limit - entry.count, 0)
            return True, remaining, 0

    def reset_epoch(self, now: float) -> int:
        window_start = int(now // self.window_s) * self.window_s
        return window_start + self.window_s

    def log_hash(self, key: str) -> str:
        return _log_hash(key, self.hash_secret)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window per-API-key limiter for POST /mcp."""

    def __init__(self, app, cfg: HttpConfig):
        super().__init__(app)
        self.cfg = cfg
        self.enabled = not (
            cfg.rate_limit_allow_disable
            and cfg.rate_limit_rpm == 0
            and cfg.env in {"dev", "local"}
        )
        self.limiter = _FixedWindowLimiter(
            limit=cfg.rate_limit_rpm if self.enabled else 1_000_000_000,
            window_s=cfg.rate_limit_window_s,
            max_keys=cfg.rate_limit_max_keys,
            ttl_windows=cfg.rate_limit_ttl_windows,
            hash_secret=cfg.rate_limit_hash_secret,
        )

    def _applies(self, request: Request) -> bool:
        return (
            self.enabled
            and request.method.upper() == "POST"
            and request.url.path == self.cfg.path
        )

    async def dispatch(self, request: Request, call_next: Callable):
        if not self._applies(request):
            return await call_next(request)

        rid = getattr(request.state, "request_id", "")
        now = time.time()
        api_key = request.headers.get("X-OpenProject-Key") or ""
        allowed, remaining, retry_after = await self.limiter.check_and_increment(
            api_key, now
        )
        reset_epoch = self.limiter.reset_epoch(now)

        if not allowed:
            return self._limited_response(retry_after, reset_epoch, rid)

        response: Response = await call_next(request)
        self._apply_headers(response, remaining, reset_epoch, rid)
        return response

    def _limited_response(
        self, retry_after: int, reset_epoch: int, request_id: str
    ) -> Response:
        payload = {
            "error": "rate_limited",
            "message": "Rate limit exceeded",
            "retry_after_s": retry_after,
            "request_id": request_id,
        }
        headers = self._rate_headers(0, reset_epoch, request_id)
        headers["Retry-After"] = str(retry_after)
        return Response(
            json.dumps(payload),
            status_code=429,
            media_type="application/json",
            headers=headers,
        )

    def _apply_headers(
        self, response: Response, remaining: int, reset_epoch: int, request_id: str
    ) -> None:
        headers = self._rate_headers(remaining, reset_epoch, request_id)
        for k, v in headers.items():
            response.headers.setdefault(k, v)

    def _rate_headers(
        self, remaining: int, reset_epoch: int, request_id: str
    ) -> Dict[str, str]:
        headers = {
            "X-RateLimit-Limit": str(self.cfg.rate_limit_rpm),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_epoch),
            "X-RateLimit-Policy": f"fixed-window;w={self.cfg.rate_limit_window_s};limit={self.cfg.rate_limit_rpm}",  # noqa: E501
        }
        if request_id:
            headers["X-Request-Id"] = request_id
        return headers


class SSEHandshakeRateLimitMiddleware(BaseHTTPMiddleware):
    """Optional limiter for SSE handshake only (not the stream)."""

    def __init__(self, app, cfg: HttpConfig):
        super().__init__(app)
        self.cfg = cfg
        self.enabled = cfg.enable_sse and cfg.rate_limit_sse_rpm > 0
        self.limiter = _FixedWindowLimiter(
            limit=cfg.rate_limit_sse_rpm if self.enabled else 1_000_000_000,
            window_s=cfg.rate_limit_window_s,
            max_keys=cfg.rate_limit_max_keys,
            ttl_windows=cfg.rate_limit_ttl_windows,
            hash_secret=cfg.rate_limit_hash_secret,
        )

    def _applies(self, request: Request) -> bool:
        return self.enabled and request.url.path == "/mcp-sse"

    async def dispatch(self, request: Request, call_next: Callable):
        if not self._applies(request):
            return await call_next(request)

        rid = getattr(request.state, "request_id", "")
        now = time.time()
        api_key = request.headers.get("X-OpenProject-Key") or ""
        allowed, remaining, retry_after = await self.limiter.check_and_increment(
            api_key, now
        )
        reset_epoch = self.limiter.reset_epoch(now)

        if not allowed:
            payload = {
                "error": "rate_limited",
                "message": "SSE rate limit exceeded",
                "retry_after_s": retry_after,
                "request_id": rid,
            }
            headers = {
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(self.cfg.rate_limit_sse_rpm),
                "X-RateLimit-Remaining": str(0),
                "X-RateLimit-Reset": str(reset_epoch),
                "X-RateLimit-Policy": f"fixed-window;w={self.cfg.rate_limit_window_s};limit={self.cfg.rate_limit_sse_rpm}",  # noqa: E501
            }
            if rid:
                headers["X-Request-Id"] = rid
            return Response(
                json.dumps(payload),
                status_code=429,
                media_type="application/json",
                headers=headers,
            )

        response: Response = await call_next(request)
        response.headers.setdefault(
            "X-RateLimit-Limit", str(self.cfg.rate_limit_sse_rpm)
        )
        response.headers.setdefault("X-RateLimit-Remaining", str(remaining))
        response.headers.setdefault("X-RateLimit-Reset", str(reset_epoch))
        response.headers.setdefault(
            "X-RateLimit-Policy",
            f"fixed-window;w={self.cfg.rate_limit_window_s};limit={self.cfg.rate_limit_sse_rpm}",
        )
        if rid:
            response.headers.setdefault("X-Request-Id", rid)
        return response


__all__ = [
    "RateLimitMiddleware",
    "SSEHandshakeRateLimitMiddleware",
]
