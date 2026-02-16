# Transport: HTTP vs stdio (Stage 2.1)

## Decision
- **Chosen runner:** FastMCP native Streamable HTTP (Option A).
- **Fallback:** Switch to an ASGI wrapper (FastAPI/Starlette) only if FastMCP cannot provide: JSON responses, stateless mode, configurable `/mcp` path, pre-routing middleware hooks, or notification 202 handling. Currently no blockers in the allowed version range.
- **SSE:** Not required; JSON response mode is the default. `GET /mcp` exists in FastMCP but returns `406 Not Acceptable` unless the client requests `text/event-stream`; with SSE disabled, clients should use POST only. FastMCP still expects `Accept` to include both `application/json` and `text/event-stream`; it will respond with JSON when `FASTMCP_JSON_RESPONSE=1`.
- **Accept (compat mode):** The adapter normalizes Accept for JSON-first behavior. If Accept is missing, `*/*`, `application/*`, or includes `application/json` → JSON response. If Accept is **only** `text/event-stream` while SSE is disabled → 406 JSON error. `GET /mcp` returns 405 when SSE is disabled.
- **Host/DNS rebinding:** For Stage 2.1 we explicitly disable DNS-rebinding protection in the transport settings to keep in-process tests simple. A dedicated security ticket (2.9) will re-enable this with an allowlist.

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
- Env overrides: `FASTMCP_HOST`, `FASTMCP_PORT`, `FASTMCP_STREAMABLE_HTTP_PATH`, `FASTMCP_JSON_RESPONSE`, `FASTMCP_STATELESS_HTTP`

## Required versions / deps
- `mcp[cli]` >= 1.11.0, explicitly excluding 1.12.0–1.12.1 due to reported Streamable HTTP regressions. Version guard is enforced in tests.
- HTTP extras: install with `pip install .[http]` (uvicorn, starlette). Core/stdio remains dependency-light.

## Test coverage (added in Stage 2.1)
- In-process ASGI tests: initialize (200 JSON), tools/list (200 JSON with tools present), notification-only (202, JSON headers), JSON-only assertion (no `text/event-stream`), and GET without SSE Accept returns 405/406.

## Notes for later stages
- Auth, rate limiting, request-id, CORS/security headers, health/readiness, and SSE (if ever required) will be added via middleware/hooks in later tickets.
