# Context contract

## ContextVars

- `api_key`
- `base_url`
- `request_id`
- `user_agent`

## Precedence

- HTTP:
  `X-OpenProject-Key` -> `Authorization: Bearer <api-key>` -> `X-API-Key` -> `OPENPROJECT_API_KEY`
- Stdio:
  `OPENPROJECT_BASE_URL` and `OPENPROJECT_API_KEY` from env at startup

`OPENPROJECT_BASE_URL` is always env-only. Per-request base URL override is not supported.

## HTTP request contract

- Canonical auth header: `X-OpenProject-Key`
- Compatibility aliases accepted for 1.x: `X-API-Key`, `Authorization: Bearer <api-key>`
- `X-Request-Id` is optional
- `User-Agent` is optional

## Error responses

```json
{
  "error": "missing_api_key" | "missing_base_url",
  "message": "...",
  "request_id": "<id>"
}
```

- 401 for missing API key
- 500 for missing base URL
- `X-Request-Id` is echoed on the response

## Runtime behavior

- HTTP seeds context per request and resets it after the request.
- Stdio seeds context once from env during startup.
- Request IDs propagate into tool logs and outbound OpenProject client calls.

## Helpers

- `get_context()` returns `RequestContext(api_key, base_url, request_id, user_agent)`
- `seed_from_env()` bootstraps stdio from env
- `seed_from_headers()` parses HTTP request headers without mutating globals
- `apply_request_context(...)` and `reset_context(tokens)` bracket request handling
