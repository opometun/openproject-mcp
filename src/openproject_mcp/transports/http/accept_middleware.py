from __future__ import annotations

import json
from typing import Callable, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


def _parse_accept(header_value: str | None) -> Tuple[bool, bool]:
    """
    Return (has_json, has_sse) considering wildcards and q-values.
    """
    if not header_value or not header_value.strip():
        return True, False  # missing -> treat as JSON acceptable

    has_json = False
    has_sse = False
    for part in header_value.split(","):
        media_range = part.strip()
        if not media_range:
            continue
        # strip q
        if ";" in media_range:
            media_range = media_range.split(";", 1)[0].strip()
        if media_range in ("*", "*/*"):
            has_json = True
            has_sse = True
            continue
        if media_range in ("application/json", "application/*"):
            has_json = True
            continue
        if media_range == "text/event-stream":
            has_sse = True
            continue
    return has_json, has_sse


class AcceptMiddleware(BaseHTTPMiddleware):
    """
    Enforce JSON-first behavior with SSE disabled.
    - If Accept includes JSON (or is */* or missing), pass through.
    - If Accept is SSE-only, return 406 with JSON error.
    - GET /mcp returns 405 (SSE disabled).
    """

    async def dispatch(self, request: Request, call_next: Callable):
        # Handle GET /mcp early: SSE is disabled
        if request.method.upper() == "GET" and request.url.path == "/mcp":
            rid = getattr(request.state, "request_id", "")
            return Response(
                json.dumps(
                    {
                        "error": "method_not_allowed",
                        "message": "SSE is disabled; GET /mcp not supported.",
                        "request_id": rid,
                    }
                ),
                status_code=405,
                media_type="application/json",
                headers={"X-Request-Id": rid} if rid else None,
            )

        has_json, has_sse = _parse_accept(request.headers.get("accept"))
        if not has_json and has_sse:
            rid = getattr(request.state, "request_id", "")
            return Response(
                json.dumps(
                    {
                        "error": "not_acceptable",
                        "message": "SSE is disabled; use Accept: application/json.",
                        "request_id": rid,
                    }
                ),
                status_code=406,
                media_type="application/json",
                headers={"X-Request-Id": rid} if rid else None,
            )

        return await call_next(request)


__all__ = ["AcceptMiddleware"]
