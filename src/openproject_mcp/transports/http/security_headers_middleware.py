from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from openproject_mcp.transports.http.config import HttpConfig
from openproject_mcp.transports.http.trusted_proxy import is_https_request


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add baseline security headers; optional CSP and HSTS."""

    def __init__(self, app, cfg: HttpConfig):
        super().__init__(app)
        self.cfg = cfg

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        self._apply(response, request)
        return response

    def _apply(self, response: Response, request: Request) -> None:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(); microphone=(); geolocation=()"
        )
        response.headers.setdefault("Cache-Control", "no-store")

        if self.cfg.csp_enabled:
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
            )

        if self.cfg.hsts_enabled and is_https_request(request, self.cfg):
            # 6 months; preload excluded intentionally
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=15552000; includeSubDomains"
            )


__all__ = ["SecurityHeadersMiddleware"]
