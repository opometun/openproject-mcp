# Transport: HTTP vs stdio (Stage 2.17)

## Quick run
- HTTP: `python -m openproject_mcp.transports.http.main` (or Docker). Needs `OPENPROJECT_BASE_URL`; API key via env or `X-OpenProject-Key`. Health: `/healthz`, `/readyz`.
- Stdio: `python -m openproject_mcp.transports.stdio.main`. Uses env for base_url/api_key; no headers.

## Required envs & headers

| Transport | Required env | Required headers | Optional headers |
|-----------|--------------|------------------|------------------|
| HTTP      | `OPENPROJECT_BASE_URL` (env only) | `X-OpenProject-Key` (unless set in env) | `X-Request-Id`, `User-Agent` |
| Stdio     | `OPENPROJECT_BASE_URL`, `OPENPROJECT_API_KEY` | none | n/a |

Notes:
- Base URL header is not implemented/ignored; use env.
- `X-Request-Id` is echoed; generated if missing.

## Accept rules (HTTP)
- No `Accept` header → allowed (treated as JSON).
- `*/*` → allowed.
- `application/json` or `application/*` → allowed.
- `text/event-stream` **only** (SSE disabled) → 406.
- `GET /mcp` (SSE disabled) → 405.

## Defaults (canonical)
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
| timeout_status | 504 (allowed: 408/503/504) | MCP_TIMEOUT_STATUS |
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
| trusted_proxies | (empty) | MCP_TRUSTED_PROXIES |
| health endpoints | /healthz, /readyz | n/a |

## Policies (behavior)
- **Limits/timeouts:** POST `/mcp` enforces `max_body_bytes`; body+handler time bounded by `request_timeout_s`; timeout status uses `MCP_TIMEOUT_STATUS`. 413 on body over limit; timeout returns configured status.
- **Rate limiting:** Fixed window per API key; returns 429 with `X-RateLimit-*` + optional `X-Request-Id`. SSE has its own rpm setting.
- **CORS/origin:** Empty allowlist denies cross-origin. `MCP_ALLOWED_ORIGINS` exact-match scheme/host/port. `MCP_DEV_ALLOW_LOCALHOST` (dev/local only + empty allowlist) auto-allows localhost/127. `MCP_ALLOW_CREDENTIALS` controls credentials. Exposed headers include `X-Request-Id`.
- **Security headers:** nosniff, frame deny, referrer none, permissions policy, cache-control no-store. Optional CSP/HSTS per env; HSTS only when HTTPS (direct or trusted proxy).
- **SSE:** Disabled by default. With SSE disabled: `GET /mcp` → 405; `text/event-stream` only → 406. When enabled, SSE at `/mcp-sse`; handshake limiter uses SSE rpm config.
- **Host/DNS rebinding:** Allowed host list derived from configured host, dev localhost toggle, and allowlisted origins; DNS rebinding protection enabled.

## Compatibility / client tips
- Always send `Content-Type: application/json` on POST.
- Send `Accept: application/json` (or include it) to avoid 406 when using SSE-only Accept.
- Provide API key via `X-OpenProject-Key` unless set in env.
- For curl/httpx examples, see README and tests; health at `/healthz`, readiness at `/readyz`.

## Troubleshooting
- 401 `missing_api_key`: set `OPENPROJECT_API_KEY` or `X-OpenProject-Key`.
- 500 `missing_base_url`: set `OPENPROJECT_BASE_URL` (env-only).
- 405 on `GET /mcp`: use POST or enable SSE.
- 406 on `Accept: text/event-stream` (SSE disabled): include `application/json` or enable SSE.
- 413 `payload_too_large`: raise `MCP_MAX_BODY_BYTES`.
- 429 `rate_limited`: respect `Retry-After`, increase rpm/window, or slow requests.
- Timeout status (default 504): increase `MCP_REQUEST_TIMEOUT_S` or adjust handler; status configurable via `MCP_TIMEOUT_STATUS`.
- CORS blocked: set `MCP_ALLOWED_ORIGINS` (or dev localhost toggle) and ensure origin matches scheme/host/port exactly; note credentials flag if needed.
