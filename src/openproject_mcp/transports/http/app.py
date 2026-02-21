from __future__ import annotations

import json
import logging

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import Response

from openproject_mcp.core.context import client_from_context
from openproject_mcp.core.registry import register_discovered_tools
from openproject_mcp.transports.http.accept_middleware import AcceptMiddleware
from openproject_mcp.transports.http.config import HttpConfig
from openproject_mcp.transports.http.max_body_middleware import MaxBodyMiddleware
from openproject_mcp.transports.http.message_middleware import MessageHandlingMiddleware
from openproject_mcp.transports.http.middleware import ContextMiddleware
from openproject_mcp.transports.http.origin_cors_middleware import (
    OriginCorsMiddleware,
    dev_localhost_allowlist,
)
from openproject_mcp.transports.http.rate_limit import (
    RateLimitMiddleware,
    SSEHandshakeRateLimitMiddleware,
)
from openproject_mcp.transports.http.security_headers_middleware import (
    SecurityHeadersMiddleware,
)
from openproject_mcp.transports.http.timeout_middleware import TimeoutMiddleware

log = logging.getLogger(__name__)


def build_fastmcp(cfg: HttpConfig | None = None) -> FastMCP:
    """Create and configure a FastMCP instance with registered tools."""
    cfg = cfg or HttpConfig.from_env()

    def _origin_to_str(spec):
        default_port = 80 if spec.scheme == "http" else 443
        if spec.port == default_port:
            return f"{spec.scheme}://{spec.host}"
        return f"{spec.scheme}://{spec.host}:{spec.port}"

    allowed_origins: list[str] = [_origin_to_str(spec) for spec in cfg.allowed_origins]

    # Dev localhost allowlist uses port=None (any); use wildcard for transport security
    for spec in dev_localhost_allowlist(cfg):
        if spec.port is None:
            allowed_origins.append(f"{spec.scheme}://{spec.host}:*")
        else:
            allowed_origins.append(_origin_to_str(spec))

    allowed_hosts = [cfg.host, "testserver"]
    if cfg.dev_allow_localhost:
        allowed_hosts.extend(["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"])
    # Include hosts from allowlisted origins (with port if non-default)
    for spec in cfg.allowed_origins:
        host_port = f"{spec.host}:{spec.port}"
        for h in (spec.host, host_port):
            if h not in allowed_hosts:
                allowed_hosts.append(h)

    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )

    fastmcp = FastMCP(
        "openproject-mcp",
        json_response=cfg.json_response,
        stateless_http=cfg.stateless_http,
        streamable_http_path=cfg.path,
        host=cfg.host,
        port=cfg.port,
        transport_security=transport_security,
    )

    register_discovered_tools(fastmcp, client_from_context)

    log.info(
        "Built FastMCP (json_response=%s, stateless_http=%s, path=%s, host=%s, port=%s)",  # noqa: E501
        cfg.json_response,
        cfg.stateless_http,
        cfg.path,
        cfg.host,
        cfg.port,
    )
    return fastmcp


def build_http_app(cfg: HttpConfig | None = None):
    """Return a Starlette app ready to serve Streamable HTTP requests."""
    cfg = cfg or HttpConfig.from_env()
    fastmcp = build_fastmcp(cfg)
    app = fastmcp.streamable_http_app()
    # Add from innermost to outermost (Starlette inserts at front), desired exec:
    # Security -> Origin -> Timeout -> Accept -> Context -> RateLimit -> MaxBody -> Message -> app  # noqa: E501
    app.add_middleware(MessageHandlingMiddleware)
    app.add_middleware(MaxBodyMiddleware, cfg=cfg)
    app.add_middleware(RateLimitMiddleware, cfg=cfg)
    app.add_middleware(ContextMiddleware)
    app.add_middleware(AcceptMiddleware)
    app.add_middleware(TimeoutMiddleware, cfg=cfg)
    app.add_middleware(OriginCorsMiddleware, cfg=cfg)
    app.add_middleware(SecurityHeadersMiddleware, cfg=cfg)
    # Mount SSE endpoint separately
    app.mount(
        "/mcp-sse",
        _build_sse_app(fastmcp, cfg),
        name="mcp-sse",
    )
    return app


def _build_sse_app(fastmcp: FastMCP, cfg: HttpConfig):
    if not cfg.enable_sse:

        async def disabled_app(scope, receive, send):
            if scope.get("type") == "http":
                resp = Response(
                    json.dumps({"error": "sse_disabled", "message": "SSE not enabled"}),
                    status_code=405,
                    media_type="application/json",
                )
                await resp(scope, receive, send)
                return
            await fastmcp.streamable_http_app()(scope, receive, send)

        return disabled_app

    sse_starlette = fastmcp.sse_app(mount_path="/mcp-sse")
    # Order: Security outermost, then Origin, then optional SSE handshake limiter (no timeout/max-body on SSE)  # noqa: E501
    sse_starlette.add_middleware(SSEHandshakeRateLimitMiddleware, cfg=cfg)
    sse_starlette.add_middleware(OriginCorsMiddleware, cfg=cfg)
    sse_starlette.add_middleware(SecurityHeadersMiddleware, cfg=cfg)
    # keepalive best-effort; FastMCP may ignore if unsupported
    sse_starlette.state.sse_keepalive_s = cfg.sse_keepalive_s
    return sse_starlette


__all__ = ["HttpConfig", "build_http_app", "build_fastmcp"]
