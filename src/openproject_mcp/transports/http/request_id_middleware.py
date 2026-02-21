from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from openproject_mcp.core.observability import log_event

REQUEST_ID_HEADER = "X-Request-Id"
CORRELATION_ID_HEADER = "X-Correlation-Id"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Ensure every request has a request_id before any early-return middleware runs.
    - Accepts X-Request-Id or X-Correlation-Id.
    - Generates UUID4 hex when absent/blank.
    - Stores on request.state.request_id and echoes X-Request-Id on responses.
    - Logs duration if downstream returns successfully.
    """

    async def dispatch(self, request: Request, call_next):
        rid = (
            request.headers.get(REQUEST_ID_HEADER)
            or request.headers.get(CORRELATION_ID_HEADER)
            or ""
        ).strip()
        if not rid:
            rid = uuid.uuid4().hex

        request.state.request_id = rid

        start = time.perf_counter()
        response: Response | None = None
        status_code: int | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)
            if response is not None:
                response.headers.setdefault(REQUEST_ID_HEADER, rid)
                response.headers.setdefault("X-Request-Duration-Ms", str(duration_ms))

            # Structured, no secrets; log even on unhandled errors
            log_event(
                "http_request",
                request_id=rid,
                method=request.method.upper(),
                path=request.url.path,
                endpoint=request.url.path,
                status=status_code if status_code is not None else "exception",
                duration_ms=duration_ms,
            )
            if response is None:
                # Re-raise the original exception; logging happens above
                pass


__all__ = ["RequestIdMiddleware", "REQUEST_ID_HEADER", "CORRELATION_ID_HEADER"]
