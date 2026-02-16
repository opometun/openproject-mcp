from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from openproject_mcp.core.context import client_from_context
from openproject_mcp.core.registry import register_discovered_tools
from openproject_mcp.transports.http.accept_middleware import AcceptMiddleware
from openproject_mcp.transports.http.middleware import ContextMiddleware

from .config import HttpConfig

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
    # Inject Accept middleware (JSON-first compat) then context middleware
    app.add_middleware(AcceptMiddleware)
    app.add_middleware(ContextMiddleware)
    return app


__all__ = ["HttpConfig", "build_http_app", "build_fastmcp"]
