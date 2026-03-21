# Transport: HTTP and stdio

## Contract summary

- Supported transports: HTTP and stdio.
- `OPENPROJECT_BASE_URL` is env-only for both transports.
- HTTP uses API-key auth only.
- Canonical HTTP auth header: `X-OpenProject-Key`.
- Compatibility aliases accepted for 1.x: `X-API-Key`, `Authorization: Bearer <api-key>`.

## Quick run

- HTTP: `python -m openproject_mcp.transports.http.main`
- Stdio: `python -m openproject_mcp.transports.stdio.main`

## Required configuration

| Transport | Required env | API key source |
|-----------|--------------|----------------|
| HTTP | `OPENPROJECT_BASE_URL` | `X-OpenProject-Key` or `OPENPROJECT_API_KEY` |
| Stdio | `OPENPROJECT_BASE_URL`, `OPENPROJECT_API_KEY` | env only |

Notes:
- Per-request base URL override is not supported.
- `X-Request-Id` is optional and echoed back when present.

## Defaults

| Setting | Default | Env |
|---------|---------|-----|
| host | 127.0.0.1 | FASTMCP_HOST |
| port | 8000 | FASTMCP_PORT |
| path | /mcp | FASTMCP_STREAMABLE_HTTP_PATH |
| json_response | true | FASTMCP_JSON_RESPONSE |
| stateless_http | true | FASTMCP_STATELESS_HTTP |
| SSE enabled | false | MCP_ENABLE_SSE |
| SSE keepalive (s) | 15 | MCP_SSE_KEEPALIVE_S |
| max_body_bytes | 1_000_000 | MCP_MAX_BODY_BYTES |
| request_timeout_s | 30 | MCP_REQUEST_TIMEOUT_S |
| timeout_status | 504 | MCP_TIMEOUT_STATUS |
| rate_limit_rpm | 60 | MCP_RATE_LIMIT_RPM |
| rate_limit_window_s | 60 | MCP_RATE_LIMIT_WINDOW_S |
| rate_limit_max_keys | 10_000 | MCP_RATE_LIMIT_MAX_KEYS |
| rate_limit_ttl_windows | 3 | MCP_RATE_LIMIT_TTL_WINDOWS |
| rate_limit_sse_rpm | 10 | MCP_RATE_LIMIT_SSE_RPM |
| allow_disable_limits | false | MCP_ALLOW_DISABLE_LIMITS |
| allow_disable_rate_limit (dev/local only) | false | MCP_RATE_LIMIT_ALLOW_DISABLE |
| allowed_origins | empty (deny) | MCP_ALLOWED_ORIGINS |
| dev_allow_localhost | false | MCP_DEV_ALLOW_LOCALHOST |
| allow_credentials | false | MCP_ALLOW_CREDENTIALS |
| cors_max_age | 0 | MCP_CORS_MAX_AGE |
| hsts_enabled | false | MCP_HSTS_ENABLED |
| csp_enabled | false | MCP_CSP_ENABLED |
| trust_proxy_headers | false | MCP_TRUST_PROXY_HEADERS |
| trusted_proxies | empty | MCP_TRUSTED_PROXIES |
| health endpoints | /healthz, /readyz | n/a |

## HTTP behavior

- `POST /mcp` accepts JSON requests.
- Missing `Accept`, `*/*`, `application/json`, and `application/*` are allowed.
- `GET /mcp` returns 405 when SSE is disabled.
- `Accept: text/event-stream` alone returns 406 when SSE is disabled.
- `GET /healthz` and `GET /readyz` are available without auth.

## Troubleshooting

- 401 `missing_api_key`: send `X-OpenProject-Key` or set `OPENPROJECT_API_KEY`.
- 500 `missing_base_url`: set `OPENPROJECT_BASE_URL`.
- 405 on `GET /mcp`: use `POST /mcp` or enable SSE.
- 406 on `Accept: text/event-stream`: include `application/json` or enable SSE.
- 413 `payload_too_large`: raise `MCP_MAX_BODY_BYTES`.
- 429 `rate_limited`: respect `Retry-After` or adjust rate-limit config.
