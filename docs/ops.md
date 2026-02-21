# Operations: Health and Readiness (Stage 2.13)

## Endpoints
- `GET /healthz` — liveness; 200 `{"status":"ok"}`; no headers required; `Cache-Control: no-store`.
- `GET /readyz` — readiness; 200 when all checks pass, else 503 with machine-readable payload; no headers required; `Cache-Control: no-store`.

### Readiness payload
```json
{
  "status": "ok" | "fail",
  "checks": {
    "config_loaded": true,
    "limiter_config_valid": true,
    "default_base_url_present": false,
    "default_api_key_present": true,
    "header_override_supported": true
  },
  "failed": ["default_base_url_present"]
}
```

- `failed` lists the keys that are false. No external connectivity checks are performed for determinism.
- `default_base_url_present` / `default_api_key_present` come from env at startup (no dotenv). If either is missing, `status: "fail"` and 503.
- `header_override_supported` reflects that API key can be provided per request; base URL override is not currently supported.

## Middleware bypass
`/healthz` and `/readyz` are dispatched via a minimal ops sub-app before the main middleware stack, so they are not subject to auth, rate limits, body parsing, Accept rules, or JSON-RPC handling.

## Scope
Applies to the HTTP transport only; stdio transport exposes no ops endpoints in this stage.
