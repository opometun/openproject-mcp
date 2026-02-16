from __future__ import annotations

import os
from dataclasses import dataclass
from ipaddress import ip_network
from typing import Iterable, List, Tuple
from urllib.parse import urlsplit


def _idna_lower(host: str) -> str:
    """Lowercase + IDNA encode/strip dot; raise on failure."""
    host = host.strip().rstrip(".")
    return host.encode("idna").decode("ascii").lower()


@dataclass(frozen=True)
class OriginSpec:
    """Normalized origin tuple. port=None means any port (dev localhost only)."""

    scheme: str
    host: str
    port: int | None

    def matches(self, scheme: str, host: str, port: int) -> bool:
        if self.scheme != scheme or self.host != host:
            return False
        return self.port is None or self.port == port


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


def _split_csv_env(name: str) -> List[str]:
    raw = os.getenv(name, "")
    return [part.strip() for part in raw.split(",") if part.strip()]


def _normalize_origin(origin: str) -> OriginSpec:
    if origin is None:
        raise ValueError("Origin is required")
    raw = origin.strip()
    if not raw or raw.lower() == "null":
        raise ValueError("Null origin not allowed")

    parts = urlsplit(raw)
    if not parts.scheme or not parts.netloc:
        raise ValueError(f"Invalid origin: {origin}")
    if parts.path not in {"", "/"} or parts.query or parts.fragment:
        raise ValueError("Origin must not include path, query, or fragment")

    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("Origin scheme must be http or https")

    if not parts.hostname:
        raise ValueError("Origin host missing")
    host = _idna_lower(parts.hostname)

    port = parts.port
    if port is None:
        port = 80 if scheme == "http" else 443

    return OriginSpec(scheme=scheme, host=host, port=port)


def _normalize_origin_list(origins: Iterable[str]) -> Tuple[OriginSpec, ...]:
    normalized = []
    for origin in origins:
        normalized.append(_normalize_origin(origin))
    return tuple(normalized)


@dataclass(frozen=True)
class HttpConfig:
    """Minimal configuration for the HTTP transport runner."""

    host: str = "127.0.0.1"
    port: int = 8000
    path: str = "/mcp"
    json_response: bool = True
    stateless_http: bool = True
    enable_sse: bool = False
    sse_keepalive_s: int = 15
    allowed_origins: Tuple[OriginSpec, ...] = ()
    dev_allow_localhost: bool = False
    allow_credentials: bool = False
    cors_max_age: int = 0
    csp_enabled: bool = False
    hsts_enabled: bool = False
    trust_proxy_headers: bool = False
    trusted_proxies: Tuple[str, ...] = ()
    env: str = ""
    exposed_headers: Tuple[str, ...] = ("X-Request-Id",)
    allowed_headers: Tuple[str, ...] = (
        "Content-Type",
        "Accept",
        "X-OpenProject-Key",
        "X-Request-Id",
        "X-OpenProject-BaseUrl",
    )

    @classmethod
    def from_env(cls) -> "HttpConfig":
        env = os.getenv("MCP_ENV", "").lower()
        allowed_origins = _normalize_origin_list(_split_csv_env("MCP_ALLOWED_ORIGINS"))
        dev_allow_localhost = _get_bool_env("MCP_DEV_ALLOW_LOCALHOST", False)

        if dev_allow_localhost:
            if env not in {"dev", "local"}:
                raise ValueError(
                    "MCP_DEV_ALLOW_LOCALHOST=true requires MCP_ENV=dev or MCP_ENV=local"
                )
            if allowed_origins:
                raise ValueError(
                    "MCP_DEV_ALLOW_LOCALHOST=true requires MCP_ALLOWED_ORIGINS to be empty"  # noqa: E501
                )

        allow_credentials = _get_bool_env("MCP_ALLOW_CREDENTIALS", False)
        cors_max_age = int(os.getenv("MCP_CORS_MAX_AGE", "0") or 0)
        csp_enabled = _get_bool_env("MCP_CSP_ENABLED", False)
        hsts_enabled = _get_bool_env("MCP_HSTS_ENABLED", False)
        trust_proxy_headers = _get_bool_env("MCP_TRUST_PROXY_HEADERS", False)
        trusted_proxies_raw = _split_csv_env("MCP_TRUSTED_PROXIES")

        if trust_proxy_headers and not trusted_proxies_raw:
            raise ValueError(
                "MCP_TRUSTED_PROXIES must be set when MCP_TRUST_PROXY_HEADERS is true"
            )

        trusted_proxies: List[str] = []
        for item in trusted_proxies_raw:
            # Validate format early
            ip_network(item, strict=False)
            trusted_proxies.append(item)

        return cls(
            host=os.getenv("FASTMCP_HOST", cls.host),
            port=int(os.getenv("FASTMCP_PORT", cls.port)),
            path=os.getenv("FASTMCP_STREAMABLE_HTTP_PATH", cls.path),
            json_response=_get_bool_env("FASTMCP_JSON_RESPONSE", cls.json_response),
            stateless_http=_get_bool_env("FASTMCP_STATELESS_HTTP", cls.stateless_http),
            enable_sse=_get_bool_env("MCP_ENABLE_SSE", cls.enable_sse),
            sse_keepalive_s=int(os.getenv("MCP_SSE_KEEPALIVE_S", cls.sse_keepalive_s)),
            allowed_origins=allowed_origins,
            dev_allow_localhost=dev_allow_localhost,
            allow_credentials=allow_credentials,
            cors_max_age=cors_max_age,
            csp_enabled=csp_enabled,
            hsts_enabled=hsts_enabled,
            trust_proxy_headers=trust_proxy_headers,
            trusted_proxies=tuple(trusted_proxies),
            env=env,
        )


__all__ = ["HttpConfig", "OriginSpec", "_normalize_origin", "_idna_lower"]
