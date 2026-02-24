# openproject-mcp
MCP Server for OpenProject: a lightweight bridge that exposes OpenProject work items, projects, users, and workflows as tool-ready endpoints for LLM agents—supporting search, retrieval, creation/updates, and automation with secure auth and clear schemas.

## Smoke Test

Run an end-to-end check (list projects → create WP → update status → verify):

```bash
OPENPROJECT_BASE_URL="https://your-op.example.com" \
OPENPROJECT_API_KEY="your-api-key" \
python -m scripts.smoke_test
```

Optional env overrides:
- `TEST_PROJECT_ID` or `TEST_PROJECT_IDENTIFIER` — pick a specific project; otherwise first project is used.
- `TEST_WP_TYPE` — desired type name (default tries Bug → Task → first available).
- `TEST_TARGET_STATUS` — desired status name (default tries In Progress → first non-closed → first).
- `SMOKE_TEST_CLEANUP=1` — attempt a simple cleanup step (default leaves the created WP).

The script prints human-readable steps and exits non-zero on failure.

## Package layout (Stage 2.2)
- Core, transport-agnostic code lives in `openproject_mcp/core/`.
- Transports live in `openproject_mcp/transports/{stdio,http}/`.
- Compatibility shims keep `openproject_mcp.client`, `hal`, `models`, and `server_registry` working; prefer the new `openproject_mcp.core.*` imports. Shims are slated for removal in a future release.

## Docker (HTTP transport)
- Build: `docker build -t openproject-mcp .`
- Run: `docker run -p 8000:8000 -e OPENPROJECT_BASE_URL=http://example.com -e OPENPROJECT_API_KEY=your-key openproject-mcp`
- Health endpoints: `GET /healthz`, `GET /readyz`
- API key can also be supplied per request via the `X-OpenProject-Key` header.

## Run modes (quick)
- **HTTP (default):** `python -m openproject_mcp.transports.http.main` or the Docker run above. Requires `OPENPROJECT_BASE_URL`; API key via env or `X-OpenProject-Key`. Accept rules: missing/`*/*`/`application/json` are allowed; `text/event-stream` only → 406 when SSE disabled. `GET /mcp` → 405 when SSE disabled. Health: `/healthz`, `/readyz`.
- **Stdio:** `python -m openproject_mcp.transports.stdio.main`. Seeds ContextVars once from env (`OPENPROJECT_BASE_URL`, `OPENPROJECT_API_KEY`); no headers used.

See `docs/transport.md` for the canonical defaults table (limits, timeouts, rate limits, CORS, host/port/path) and troubleshooting.

## Unified CLI (openproject-mcp)
Install (editable or wheel) then use the single entrypoint:

```bash
openproject-mcp stdio
openproject-mcp http --host 0.0.0.0 --port 8080
```

Config & precedence (highest → lowest):
1) CLI flags (`--host`, `--port`, `--log-level`, `--config`)
2) Environment (`MCP_HTTP_HOST`, `MCP_HTTP_PORT`, `MCP_LOG_LEVEL`/`OPENPROJECT_LOG_LEVEL`)
3) TOML config file if provided via `--config` (keys: `host`, `port`, `log_level`)
4) Defaults: host `127.0.0.1`, port `8080`, log-level `info`

Logging: stdio mode logs to stderr only; HTTP uses standard stderr logging (uvicorn-compatible).

## Installation
- Base (stdio only): `pip install openproject-mcp`
- HTTP transport: `pip install "openproject-mcp[http]"`

Dockerfile already installs the HTTP extra; local HTTP runs need the extra or you’ll see a friendly error telling you to install it.

## OAuth scopes (when enabled)
- Tools may declare required scopes via `@requires_scopes(...)`. These scopes are checked against the JWT `scope`/`scopes` claim.
- API-key callers have no scopes; scope-gated tools will reject API-key requests. Use OAuth for those tools.
- Issuer/audience/JWKS are configurable via `OAUTH_ISSUER`, `OAUTH_AUDIENCE`, `OAUTH_JWKS_URL` (CSV for multi-issuer); required global scopes via `OAUTH_REQUIRED_SCOPES` (CSV).

### Per-tool scopes

| Scope | Tools |
|-------|-------|
| `wp:write` | `create_work_package`, `update_status`, `update_work_package`, `append_work_package_description` |
| `wp:comment` | `add_comment` |
| `time:write` | `log_time` |
| `attachment:write` | `attach_file_to_wp` |

Read-only tools (`list_work_packages`, `get_work_package`, `list_projects`, etc.) require no scopes and work with any authenticated caller.
