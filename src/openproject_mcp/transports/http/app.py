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
from openproject_mcp.transports.http.message_middleware import MessageHandlingMiddleware
from openproject_mcp.transports.http.middleware import ContextMiddleware

log = logging.getLogger(__name__)


def build_fastmcp(cfg: HttpConfig | None = None) -> FastMCP:
    """Create and configure a FastMCP instance with registered tools."""
    cfg = cfg or HttpConfig.from_env()

    # Disable DNS rebinding protection for now (Stage 2.1); will be
    # revisited when we add explicit allowlist handling in ticket 2.9.
    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False
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
    fastmcp = build_fastmcp(cfg)
    app = fastmcp.streamable_http_app()
    # Inject Accept middleware (JSON-first compat), message handling, then context middleware  # noqa: E501
    app.add_middleware(AcceptMiddleware)
    app.add_middleware(MessageHandlingMiddleware)
    app.add_middleware(ContextMiddleware)
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
    # keepalive best-effort; FastMCP may ignore if unsupported
    sse_starlette.state.sse_keepalive_s = cfg.sse_keepalive_s
    return sse_starlette


__all__ = ["HttpConfig", "build_http_app", "build_fastmcp"]
