from __future__ import annotations

import json
from typing import Callable, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

PARSE_ERROR = -32700
INVALID_REQUEST = -32600


def _json_rpc_error(
    code: int, message: str, http_status: int = 400, request_id: str = ""
) -> Response:
    payload = {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": code, "message": message},
    }
    if request_id:
        payload["request_id"] = request_id
    return Response(
        json.dumps(payload),
        status_code=http_status,
        media_type="application/json",
    )


def _classify_payload(data) -> Tuple[str, bool]:
    """
    Returns (kind, valid) where kind in {"notification_only", "requests"}.
    valid=False means invalid request.
    """

    def is_request(obj):
        return isinstance(obj, dict) and "method" in obj

    def is_notification(obj):
        return is_request(obj) and "id" not in obj

    if isinstance(data, list):
        if len(data) == 0:
            return "invalid", False
        all_notifications = True
        for item in data:
            if not is_request(item):
                return "invalid", False
            if not is_notification(item):
                all_notifications = False
        if all_notifications:
            return "notification_only", True
        return "requests", True

    if is_request(data):
        if is_notification(data):
            return "notification_only", True
        return "requests", True

    return "invalid", False


def _make_receive(body: bytes):
    done = False

    async def receive():
        nonlocal done
        if done:
            return {"type": "http.request", "body": b"", "more_body": False}
        done = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


class MessageHandlingMiddleware(BaseHTTPMiddleware):
    """
    - Notifications-only payloads -> 202 Accepted, empty body (after auth/rate-limit).
    - Requests present -> pass through to FastMCP (JSON-RPC responses).
    - Invalid payloads -> JSON-RPC error (400).
    """

    async def dispatch(self, request: Request, call_next: Callable):
        if request.method.upper() != "POST" or request.url.path != "/mcp":
            return await call_next(request)

        raw_body = await request.body()
        try:
            data = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError:
            rid = getattr(request.state, "request_id", "")
            return _json_rpc_error(
                PARSE_ERROR, "Parse error", http_status=400, request_id=rid
            )

        kind, valid = _classify_payload(data)
        if not valid:
            rid = getattr(request.state, "request_id", "")
            return _json_rpc_error(
                INVALID_REQUEST, "Invalid Request", http_status=400, request_id=rid
            )

        if kind == "notification_only":
            return Response(status_code=202, media_type="application/json", content="")

        # Requests present: replay body for downstream
        new_request = Request(request.scope, receive=_make_receive(raw_body))
        return await call_next(new_request)


__all__ = ["MessageHandlingMiddleware"]
