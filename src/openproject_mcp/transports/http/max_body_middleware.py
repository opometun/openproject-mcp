from __future__ import annotations

import json
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from openproject_mcp.transports.http.config import (
    ERROR_PAYLOAD_TOO_LARGE,
    HttpConfig,
)


class MaxBodyMiddleware(BaseHTTPMiddleware):
    """Enforce max body size for POST /mcp before JSON parsing/tool execution."""

    def __init__(self, app, cfg: HttpConfig):
        super().__init__(app)
        self.cfg = cfg

    def _applies(self, request: Request) -> bool:
        return request.method.upper() == "POST" and request.url.path == self.cfg.path

    async def dispatch(self, request: Request, call_next: Callable):
        if not self._applies(request) or self.cfg.max_body_bytes == 0:
            return await call_next(request)

        # Fast path: Content-Length present
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                length = int(content_length)
            except ValueError:
                length = None
            else:
                if length > self.cfg.max_body_bytes:
                    return self._too_large(getattr(request.state, "request_id", ""))

        total = 0
        chunks: list[bytes] = []

        async for chunk in request.stream():
            total += len(chunk)
            if total > self.cfg.max_body_bytes:
                return self._too_large(getattr(request.state, "request_id", ""))
            chunks.append(chunk)

        body = b"".join(chunks)
        # Cache body so downstream Request.body() returns the buffered content
        request._body = body  # type: ignore[attr-defined]
        request._stream_consumed = True  # type: ignore[attr-defined]
        return await call_next(request)

    @staticmethod
    def _payload(request_id: str | None):
        return {
            "error": ERROR_PAYLOAD_TOO_LARGE,
            "message": "Body exceeds limit",
            "request_id": request_id or "",
        }

    def _too_large(self, request_id: str) -> Response:
        return Response(
            json.dumps(self._payload(request_id)),
            status_code=413,
            media_type="application/json",
            headers={"X-Request-Id": request_id} if request_id else None,
        )


__all__ = ["MaxBodyMiddleware"]
