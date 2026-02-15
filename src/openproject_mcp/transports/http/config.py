from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool_env(name: str, default: bool) -> bool:
    """Parse a boolean environment variable with a safe default."""
    raw = os.getenv(name)
    if raw is None:
        return default
    val = raw.strip().lower()
    if val in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if val in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


@dataclass(frozen=True)
class HttpConfig:
    """Minimal configuration for the HTTP transport runner."""

    host: str = "127.0.0.1"
    port: int = 8000
    path: str = "/mcp"
    json_response: bool = True
    stateless_http: bool = True

    @classmethod
    def from_env(cls) -> "HttpConfig":
        return cls(
            host=os.getenv("FASTMCP_HOST", cls.host),
            port=int(os.getenv("FASTMCP_PORT", cls.port)),
            path=os.getenv("FASTMCP_STREAMABLE_HTTP_PATH", cls.path),
            json_response=_get_bool_env("FASTMCP_JSON_RESPONSE", cls.json_response),
            stateless_http=_get_bool_env("FASTMCP_STATELESS_HTTP", cls.stateless_http),
        )
