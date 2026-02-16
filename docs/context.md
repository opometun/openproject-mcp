# Context / DI contract (Stage 2.3)

## Keys (ContextVars)
- `api_key` (required)
- `base_url` (required, deployment-static in this stage)
- `request_id` (generated if absent)
- `user_agent` (optional)

## Precedence
- HTTP adapter: headers for `X-OpenProject-Key`; base URL comes only from env defaults (header override not supported in 2.3); request_id uses `X-Request-Id` if present, otherwise generated.
- Stdio: env defaults (`OPENPROJECT_BASE_URL`, `OPENPROJECT_API_KEY`), request_id generated.
- Missing api_key ⇒ 401; missing base_url (no env) ⇒ 500 (server misconfig).

## Header contract (HTTP)
- `X-OpenProject-Key`: required
- `X-Request-Id`: optional; echoed back if provided, otherwise generated
- `User-Agent`: optional
- Base URL header not supported in 2.3.

## Error responses (HTTP middleware)
```json
{ "error": "missing_api_key" | "missing_base_url",
  "message": "...",
  "request_id": "<id>" }
```
Status: 401 for missing API key; 500 for missing base URL.
Response header: `X-Request-Id`.

## Core helper
- `openproject_mcp.core.context.get_context()` → `RequestContext(api_key, base_url, request_id, user_agent)`; raises `MissingApiKeyError` / `MissingBaseUrlError` per require flags.
- `seed_from_env()` to bootstrap env defaults (stdio).
- `seed_from_headers(headers)` to parse HTTP headers without mutating globals.
- `apply_request_context(...)` + `reset_context(tokens)` to set/reset ContextVars per request.
- `ensure_request_id()` to generate IDs.

## Examples
### HTTP request
```
curl -X POST http://127.0.0.1:8000/mcp \
  -H 'Accept: application/json, text/event-stream' \
  -H 'Content-Type: application/json' \
  -H 'X-OpenProject-Key: sk-abc123' \
  -d '{"jsonrpc":"2.0","id":"1","method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0.0.0"}}}'
```

### Stdio bootstrap
Set `OPENPROJECT_BASE_URL` and `OPENPROJECT_API_KEY`, then `python -m openproject_mcp.transports.stdio.main`. Core seeds ContextVars once from env.
