# Operations: health and readiness

## Endpoints

- `GET /healthz` returns 200 with `{"status":"ok"}`
- `GET /readyz` returns 200 when required startup checks pass, otherwise 503

Both endpoints are unauthenticated and return `Cache-Control: no-store`.

## Readiness payload

```json
{
  "status": "ok" | "fail",
  "checks": {
    "config_loaded": true,
    "limiter_config_valid": true,
    "default_base_url_present": true,
    "per_request_api_key_supported": true
  },
  "failed": []
}
```

Notes:
- `default_base_url_present` comes from env at startup.
- HTTP does not require `OPENPROJECT_API_KEY` at startup because API keys can be supplied per request.
- No external OpenProject connectivity checks are performed.

## Middleware bypass

`/healthz` and `/readyz` run outside the main MCP middleware stack, so they are not affected by auth, rate limits, JSON-RPC parsing, or Accept negotiation.
