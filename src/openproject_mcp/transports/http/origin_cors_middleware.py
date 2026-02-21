from __future__ import annotations

import json
from typing import Callable, Iterable, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from openproject_mcp.transports.http.config import (
    HttpConfig,
    OriginSpec,
    _normalize_origin,
)


def dev_localhost_allowlist(cfg: HttpConfig) -> Tuple[OriginSpec, ...]:
    if not cfg.dev_allow_localhost:
        return ()
    return (
        OriginSpec("http", "localhost", None),
        OriginSpec("http", "127.0.0.1", None),
        OriginSpec("https", "localhost", None),
        OriginSpec("https", "127.0.0.1", None),
    )


def _parse_origin_header(raw_origin: str) -> OriginSpec:
    # Reuse normalization but allow default-port resolution
    return _normalize_origin(raw_origin)


def _build_vary(value_list: Iterable[str]) -> str:
    seen = []
    for item in value_list:
        norm = item.strip()
        if norm and norm.lower() not in {v.lower() for v in seen}:
            seen.append(norm)
    return ", ".join(seen)


def _error_response(
    status: int, code: str, message: str, vary: str | None = None, request_id: str = ""
) -> Response:
    body = {"error": code, "message": message}
    if request_id:
        body["request_id"] = request_id
    headers = {"content-type": "application/json"}
    if vary:
        headers["vary"] = vary
    if request_id:
        headers["X-Request-Id"] = request_id
    return Response(json.dumps(body), status_code=status, headers=headers)


class OriginCorsMiddleware(BaseHTTPMiddleware):
    """Strict Origin allowlist + CORS handling (deny-by-default)."""

    def __init__(self, app, cfg: HttpConfig):
        super().__init__(app)
        self.cfg = cfg
        self.allowed_origins: Tuple[OriginSpec, ...] = (
            cfg.allowed_origins + dev_localhost_allowlist(cfg)
        )

    def _origin_allowed(self, origin: OriginSpec) -> bool:
        for allowed in self.allowed_origins:
            if allowed.matches(origin.scheme, origin.host, origin.port):
                return True
        return False

    async def dispatch(self, request: Request, call_next: Callable):
        origin_header = request.headers.get("origin")

        if origin_header:
            rid = getattr(request.state, "request_id", "")
            try:
                origin = _parse_origin_header(origin_header)
            except ValueError as exc:
                return _error_response(403, "origin_denied", str(exc), request_id=rid)

            if not self._origin_allowed(origin):
                return _error_response(
                    403, "origin_denied", "Origin not allowed", request_id=rid
                )

            # Handle preflight
            if request.method.upper() == "OPTIONS" and request.url.path in {
                self.cfg.path,
                "/mcp-sse",
            }:
                return self._preflight_response(request, origin)

            response: Response = await call_next(request)
            self._apply_cors_headers(response, origin)
            return response

        # No Origin header: pass through with no CORS headers
        return await call_next(request)

    def _preflight_response(self, request: Request, origin: OriginSpec) -> Response:
        allow_methods = ["POST", "OPTIONS"]
        if self.cfg.enable_sse:
            allow_methods.append("GET")

        vary = _build_vary(
            [
                "Origin",
                "Access-Control-Request-Method",
                "Access-Control-Request-Headers",
            ]
        )

        headers = {
            "Access-Control-Allow-Origin": self._origin_to_header(origin),
            "Access-Control-Allow-Methods": ", ".join(allow_methods),
            "Access-Control-Allow-Headers": ", ".join(self.cfg.allowed_headers),
            "Access-Control-Expose-Headers": ", ".join(self.cfg.exposed_headers),
            "Vary": vary,
        }

        if self.cfg.allow_credentials:
            headers["Access-Control-Allow-Credentials"] = "true"
        if self.cfg.cors_max_age > 0:
            headers["Access-Control-Max-Age"] = str(self.cfg.cors_max_age)

        return Response(status_code=204, headers=headers)

    def _apply_cors_headers(self, response: Response, origin: OriginSpec) -> None:
        response.headers["Access-Control-Allow-Origin"] = self._origin_to_header(origin)
        response.headers.setdefault("Vary", "Origin")
        # If Vary already set, merge with Origin
        if "Origin" not in [
            v.strip() for v in response.headers.get("Vary", "").split(",")
        ]:
            response.headers["Vary"] = _build_vary([response.headers["Vary"], "Origin"])

        if self.cfg.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Expose-Headers"] = ", ".join(
            self.cfg.exposed_headers
        )

    @staticmethod
    def _origin_to_header(origin: OriginSpec) -> str:
        port = (
            ""
            if (origin.scheme == "http" and origin.port == 80)
            or (origin.scheme == "https" and origin.port == 443)
            else f":{origin.port}"
        )
        return f"{origin.scheme}://{origin.host}{port}"


__all__ = ["OriginCorsMiddleware", "dev_localhost_allowlist"]
