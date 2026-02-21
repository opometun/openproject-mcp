from __future__ import annotations

import json
from typing import Callable

import anyio
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from openproject_mcp.transports.http.config import (
    ERROR_TIMEOUT,
    HttpConfig,
)


class TimeoutMiddleware(BaseHTTPMiddleware):
    """Enforce a max request handling time for POST /mcp (body read + handler)."""

    def __init__(self, app, cfg: HttpConfig):
        super().__init__(app)
        self.cfg = cfg

    def _applies(self, request: Request) -> bool:
        return request.method.upper() == "POST" and request.url.path == self.cfg.path

    async def dispatch(self, request: Request, call_next: Callable):
        if not self._applies(request) or self.cfg.request_timeout_s == 0:
            return await call_next(request)

        try:
            with anyio.fail_after(self.cfg.request_timeout_s):
                return await call_next(request)
        except TimeoutError:
            payload = {
                "error": ERROR_TIMEOUT,
                "message": "Request timed out",
                "request_id": getattr(request.state, "request_id", ""),
            }
            rid = getattr(request.state, "request_id", "")
            return Response(
                json.dumps(payload),
                status_code=self.cfg.timeout_status,
                media_type="application/json",
                headers={"X-Request-Id": rid} if rid else None,
            )


__all__ = ["TimeoutMiddleware"]
