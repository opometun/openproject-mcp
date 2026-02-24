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


# Error code strings used across middlewares/tests
ERROR_PAYLOAD_TOO_LARGE = "payload_too_large"
ERROR_TIMEOUT = "timeout"
ERROR_PARSE_ERROR = "parse_error"


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
        "Authorization",
        "X-API-Key",
        "X-OpenProject-Key",
        "X-Request-Id",
        "X-OpenProject-BaseUrl",
    )
    max_body_bytes: int = 1_000_000
    request_timeout_s: float = 30.0
    timeout_status: int = 504
    allow_disable_limits: bool = False
    rate_limit_rpm: int = 60
    rate_limit_window_s: int = 60
    rate_limit_allow_disable: bool = False
    rate_limit_max_keys: int = 10_000
    rate_limit_ttl_windows: int = 3
    rate_limit_sse_rpm: int = 10
    rate_limit_hash_secret: str | None = None
    # OAuth (optional, off by default)
    oauth_enabled: bool = False
    oauth_issuer: tuple[str, ...] = ("accounts.google.com",)
    oauth_audience: tuple[str, ...] | None = None
    oauth_jwks_url: tuple[str, ...] = ("https://www.googleapis.com/oauth2/v3/certs",)
    oauth_jwks_cache_ttl: int = 3600
    oauth_required_scopes: tuple[str, ...] = ()
    token_store_backend: str = "memory"  # memory|firestore
    token_enc_key: str | None = None

    def __post_init__(self):
        # Normalize single strings into tuples when instantiated directly
        object.__setattr__(
            self,
            "oauth_issuer",
            self._normalize_tuple(self.oauth_issuer),
        )
        object.__setattr__(
            self,
            "oauth_jwks_url",
            self._normalize_tuple(self.oauth_jwks_url),
        )
        if self.oauth_audience is not None:
            object.__setattr__(
                self, "oauth_audience", self._normalize_tuple(self.oauth_audience)
            )

    @staticmethod
    def _normalize_tuple(val):
        if val is None:
            return None
        if isinstance(val, str):
            return (val,)
        return tuple(val)

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

        allow_disable_limits = _get_bool_env("MCP_ALLOW_DISABLE_LIMITS", False)

        def _read_int_env(name: str, default: int) -> int:
            raw = os.getenv(name)
            if raw is None or raw.strip() == "":
                return default
            return int(raw.replace("_", ""))

        max_body_bytes = _read_int_env("MCP_MAX_BODY_BYTES", 1_000_000)
        request_timeout_s = float(os.getenv("MCP_REQUEST_TIMEOUT_S", "30") or 30)
        timeout_status = int(os.getenv("MCP_TIMEOUT_STATUS", "504") or 504)

        if timeout_status not in {408, 503, 504}:
            raise ValueError("MCP_TIMEOUT_STATUS must be one of 408, 503, 504")

        def _enforce_positive(name: str, value):
            if value <= 0:
                raise ValueError(f"{name} must be greater than zero")
            return value

        limits_disable_allowed = allow_disable_limits and env in {"dev", "local"}

        if not limits_disable_allowed:
            max_body_bytes = _enforce_positive("MCP_MAX_BODY_BYTES", max_body_bytes)
            request_timeout_s = _enforce_positive(
                "MCP_REQUEST_TIMEOUT_S", request_timeout_s
            )
        else:
            # In dev/local with explicit opt-in, zero disables
            if max_body_bytes < 0 or request_timeout_s < 0:
                raise ValueError("Negative limits are not allowed")

        # Rate limiting config
        rate_limit_allow_disable = _get_bool_env("MCP_RATE_LIMIT_ALLOW_DISABLE", False)
        rate_limit_rpm = _read_int_env("MCP_RATE_LIMIT_RPM", 60)
        rate_limit_window_s = _read_int_env("MCP_RATE_LIMIT_WINDOW_S", 60)
        rate_limit_max_keys = _read_int_env("MCP_RATE_LIMIT_MAX_KEYS", 10_000)
        rate_limit_ttl_windows = _read_int_env("MCP_RATE_LIMIT_TTL_WINDOWS", 3)
        rate_limit_sse_rpm = _read_int_env("MCP_RATE_LIMIT_SSE_RPM", 10)
        rate_limit_hash_secret = os.getenv("MCP_RATE_LIMIT_HASH_SECRET")

        oauth_enabled = _get_bool_env("OAUTH_ENABLED", False)
        oauth_issuer = os.getenv("OAUTH_ISSUER") or None
        oauth_audience = os.getenv("OAUTH_AUDIENCE") or None
        oauth_jwks_url = os.getenv("OAUTH_JWKS_URL") or None
        oauth_jwks_cache_ttl = int(os.getenv("OAUTH_JWKS_CACHE_TTL", "3600") or 3600)
        oauth_required_scopes = tuple(_split_csv_env("OAUTH_REQUIRED_SCOPES"))
        token_store_backend = os.getenv("OAUTH_TOKEN_STORE", "memory").lower()
        token_enc_key = os.getenv("OAUTH_TOKEN_ENCRYPTION_KEY")
        if oauth_enabled and not oauth_audience:
            raise ValueError(
                "OAUTH_AUDIENCE (Google OAuth client ID) must be set when OAUTH_ENABLED=true"  # noqa: E501
            )
        # Normalize CSV env strings to tuples; fall back to class defaults
        if oauth_issuer is not None:
            oauth_issuer = tuple(
                part.strip() for part in oauth_issuer.split(",") if part.strip()
            )
        else:
            oauth_issuer = cls.oauth_issuer
        if oauth_audience is not None:
            oauth_audience = (
                tuple(
                    part.strip() for part in oauth_audience.split(",") if part.strip()
                )
                or None
            )
        if oauth_jwks_url is not None:
            oauth_jwks_url = tuple(
                part.strip() for part in oauth_jwks_url.split(",") if part.strip()
            )
        else:
            oauth_jwks_url = cls.oauth_jwks_url

        if oauth_enabled:
            if not oauth_audience:
                raise ValueError("OAUTH_AUDIENCE must be set when OAuth is enabled")
            if len(oauth_issuer) != len(oauth_jwks_url):
                raise ValueError(
                    "OAUTH_ISSUER and OAUTH_JWKS_URL must have the same number of entries"  # noqa: E501
                )
            if len(oauth_audience) != len(oauth_issuer):
                # Allow single audience applied to all issuers
                if len(oauth_audience) != 1:
                    raise ValueError("OAUTH_AUDIENCE count must be 1 or match issuers")
        if token_store_backend not in {"memory", "firestore"}:
            raise ValueError("OAUTH_TOKEN_STORE must be 'memory' or 'firestore'")

        rl_disable_allowed = rate_limit_allow_disable and env in {"dev", "local"}
        if not rl_disable_allowed:
            if rate_limit_rpm <= 0:
                raise ValueError("MCP_RATE_LIMIT_RPM must be greater than zero")
        if rate_limit_window_s <= 0:
            raise ValueError("MCP_RATE_LIMIT_WINDOW_S must be greater than zero")
        if rate_limit_max_keys <= 0:
            raise ValueError("MCP_RATE_LIMIT_MAX_KEYS must be greater than zero")
        if rate_limit_ttl_windows <= 0:
            raise ValueError("MCP_RATE_LIMIT_TTL_WINDOWS must be greater than zero")

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
            max_body_bytes=max_body_bytes,
            request_timeout_s=request_timeout_s,
            timeout_status=timeout_status,
            allow_disable_limits=allow_disable_limits,
            rate_limit_rpm=rate_limit_rpm,
            rate_limit_window_s=rate_limit_window_s,
            rate_limit_allow_disable=rate_limit_allow_disable,
            rate_limit_max_keys=rate_limit_max_keys,
            rate_limit_ttl_windows=rate_limit_ttl_windows,
            rate_limit_sse_rpm=rate_limit_sse_rpm,
            rate_limit_hash_secret=rate_limit_hash_secret,
            oauth_enabled=oauth_enabled,
            oauth_issuer=oauth_issuer,
            oauth_audience=oauth_audience,
            oauth_jwks_url=oauth_jwks_url,
            oauth_jwks_cache_ttl=oauth_jwks_cache_ttl,
            oauth_required_scopes=oauth_required_scopes,
            token_store_backend=token_store_backend,
            token_enc_key=token_enc_key,
        )


__all__ = [
    "HttpConfig",
    "OriginSpec",
    "_normalize_origin",
    "_idna_lower",
    "ERROR_PAYLOAD_TOO_LARGE",
    "ERROR_TIMEOUT",
    "ERROR_PARSE_ERROR",
]
