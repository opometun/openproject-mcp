# Transport: HTTP vs stdio (Stage 2.9)

## Decision
- **Chosen runner:** FastMCP native Streamable HTTP (Option A).
- **Fallback:** Switch to an ASGI wrapper (FastAPI/Starlette) only if FastMCP cannot provide: JSON responses, stateless mode, configurable `/mcp` path, pre-routing middleware hooks, or notification 202 handling. Currently no blockers in the allowed version range.
- **SSE:** Not required; JSON response mode is the default. `GET /mcp` exists in FastMCP but returns `406 Not Acceptable` unless the client requests `text/event-stream`; with SSE disabled, clients should use POST only. FastMCP still expects `Accept` to include both `application/json` and `text/event-stream`; it will respond with JSON when `FASTMCP_JSON_RESPONSE=1`.
- **Accept (compat mode):** The adapter normalizes Accept for JSON-first behavior. If Accept is missing, `*/*`, `application/*`, or includes `application/json` → JSON response. If Accept is **only** `text/event-stream` while SSE is disabled → 406 JSON error. `GET /mcp` returns 405 when SSE is disabled.
- **Auth (HTTP):** `X-OpenProject-Key` required; base URL is deployment-static (no header override). Missing key → 401 JSON error; missing base URL (no env) → 500. `X-Request-Id` echoed.
- **CORS is not auth:** Origin/CORS checks only gate browser contexts. Authentication is always enforced via `X-OpenProject-Key` regardless of Origin.
- **SSE gate:** `/mcp` remains JSON-only. `/mcp-sse` exists but returns 405 unless `MCP_ENABLE_SSE=1`; when enabled it serves SSE at `/mcp-sse` (POST/GET), optional keepalive `MCP_SSE_KEEPALIVE_S` (best-effort). Browser `EventSource` is **not supported** because it cannot send `X-OpenProject-Key`; use `fetch` streaming with headers or introduce an alternate auth token (future scope).
- **Host/DNS rebinding:** DNS-rebinding protection is **enabled** with an allowlist derived from configured host + dev localhost toggle.

## How to run (HTTP)
```bash
# minimal env (dummy values ok for tooling enumeration)
export OPENPROJECT_BASE_URL="https://your-op.example.com"
export OPENPROJECT_API_KEY="your-api-key"

# transport defaults (override as needed)
export FASTMCP_HOST=127.0.0.1
export FASTMCP_PORT=8000
export FASTMCP_STREAMABLE_HTTP_PATH=/mcp
export FASTMCP_JSON_RESPONSE=1
export FASTMCP_STATELESS_HTTP=1

# run
python -m openproject_mcp.transports.http.main
```

## Curl smoke samples
Initialize (FastMCP currently expects `Accept: application/json, text/event-stream` even in JSON mode):
```bash
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"1","method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0.0.0"}}}'
```

List tools:
```bash
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"2","method":"tools/list","params":{"cursor":null}}'
```

Notification-only (returns 202):
```bash
curl -i -X POST http://127.0.0.1:8000/mcp \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"notifications/tools/list_changed","params":{}}'
```

## Configuration surface (HttpConfig defaults)
- host: `127.0.0.1`
- port: `8000`
- path: `/mcp`
- json_response: `true`
- stateless_http: `true`
- SSE: `MCP_ENABLE_SSE` (default false), `MCP_SSE_KEEPALIVE_S`
- CORS / Origin (default deny):
  - `MCP_ALLOWED_ORIGINS`: comma list, exact scheme+host+port match after normalization (IDNA, default ports applied). Empty => deny cross-origin.
  - `MCP_DEV_ALLOW_LOCALHOST` (bool, default false): only valid when `MCP_ENV` in `{dev, local}` **and** `MCP_ALLOWED_ORIGINS` empty; auto-allows `http(s)://localhost|127.0.0.1` on any port. Otherwise startup fails.
  - `MCP_ALLOW_CREDENTIALS` (default false): sets `Access-Control-Allow-Credentials`.
  - `MCP_CORS_MAX_AGE` (seconds, default 0): optional preflight cache.
  - Allowed request headers: `Content-Type, Accept, X-OpenProject-Key, X-Request-Id, X-OpenProject-BaseUrl`; exposed headers include `X-Request-Id`.
- Security headers:
  - Always: `X-Content-Type-Options=nosniff`, `X-Frame-Options=DENY`, `Referrer-Policy=no-referrer`, `Permissions-Policy=camera=(); microphone=(); geolocation=()`, `Cache-Control=no-store`.
  - `MCP_CSP_ENABLED`: adds `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none'`.
  - `MCP_HSTS_ENABLED`: adds HSTS **only** when request is HTTPS or when proxy headers are trusted and indicate HTTPS.
- Proxy trust for HTTPS/HSTS:
  - `MCP_TRUST_PROXY_HEADERS` (default false) and `MCP_TRUSTED_PROXIES` (comma IP/CIDR, required when enabled). Uses `Forwarded` proto first, fallback `X-Forwarded-Proto`; only honored when client IP is trusted.

## Required versions / deps
- `mcp[cli]` >= 1.11.0, explicitly excluding 1.12.0–1.12.1 due to reported Streamable HTTP regressions. Version guard is enforced in tests.
- HTTP extras: install with `pip install .[http]` (uvicorn, starlette). Core/stdio remains dependency-light.

## Test coverage (added in Stage 2.1)
- In-process ASGI tests: initialize (200 JSON), tools/list (200 JSON with tools present), notification-only (202, JSON headers), JSON-only assertion (no `text/event-stream`), and GET without SSE Accept returns 405/406.

## Notes for later stages
- Auth, rate limiting, request-id, CORS/security headers, health/readiness, and SSE (if ever required) will be added via middleware/hooks in later tickets.
