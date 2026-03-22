# openproject-mcp
MCP server for OpenProject with a small 1.0 surface: stdio and HTTP transports, deployment-static `OPENPROJECT_BASE_URL`, and API-key authentication only.

## Quickstart

Install the HTTP transport, set the OpenProject base URL in the environment, start the server, and send requests with `X-OpenProject-Key`.

```bash
pip install "openproject-mcp[http]"

export OPENPROJECT_BASE_URL="https://your-op.example.com"
python -m openproject_mcp.transports.http.main
```

```bash
curl -X POST http://127.0.0.1:8000/mcp \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'X-OpenProject-Key: your-api-key' \
  -d '{"jsonrpc":"2.0","id":"1","method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0.0.0"}}}'
```

## Breaking Changes in 1.0

- OAuth/JWT authentication was removed from the supported surface.
- Token-linking and link/unlink flows were removed from the supported surface.
- Canonical HTTP auth header: `X-OpenProject-Key`.
- Compatibility aliases accepted for 1.x only: `X-API-Key`, `Authorization: Bearer <api-key>`.
- Write permission is decided by OpenProject, not by local scope logic.

## 1.0 Contract

Supported:
- Transports: stdio and HTTP.
- Base URL source: `OPENPROJECT_BASE_URL` from environment only.
- Authentication: OpenProject API key only.
- Canonical HTTP auth header: `X-OpenProject-Key`.
- Current core tools: system, projects, work packages, users, memberships, queries, metadata, attachments, and time entries.
- Write tools run when a valid API key is supplied; OpenProject decides whether the key has write permission.

HTTP auth header behavior:
- Canonical: `X-OpenProject-Key`
- Compatibility aliases accepted for 1.x: `X-API-Key`, `Authorization: Bearer <api-key>`
- Quickstart and main docs use only `X-OpenProject-Key`

Run modes:
- HTTP: `python -m openproject_mcp.transports.http.main`
- Stdio: `python -m openproject_mcp.transports.stdio.main`

`OPENPROJECT_API_KEY` can still be supplied from the environment for default credentials, but the documented HTTP request path uses `X-OpenProject-Key`.

## Non-goals

Not supported in 1.0:
- OAuth or JWT authentication
- Linked-token storage
- Firestore token backends
- Multi-user auth flows
- Dynamic per-request base URL override
- Delete or archive lifecycle

## Support

Support matrix:

| Component | Versions | Validation |
|-----------|----------|------------|
| Python | 3.11, 3.13 | CI on every push and pull request |
| OpenProject | Published from the completed 1.0 release checklist | `initialize` plus `python -m scripts.smoke_test` against each claimed live version |

Release gate:
- Exact OpenProject versions for `1.0.0` must be recorded in [docs/release.md](docs/release.md) before tagging the release.
- Do not tag `1.0.0` until the release checklist is complete and the OpenProject support row is filled with exact tested versions.

Operational notes:
- HTTP defaults: `127.0.0.1:8000`
- Override HTTP host/port with `FASTMCP_HOST`, `FASTMCP_PORT`, or CLI flags
- HTTP health endpoints: `GET /healthz`, `GET /readyz`
- Stdio reads `OPENPROJECT_BASE_URL` and `OPENPROJECT_API_KEY` from env at startup
- HTTP accepts the API key from `X-OpenProject-Key` or `OPENPROJECT_API_KEY`

## Smoke Test

Run an end-to-end check against a real OpenProject instance:

```bash
OPENPROJECT_BASE_URL="https://your-op.example.com" \
OPENPROJECT_API_KEY="your-api-key" \
python -m scripts.smoke_test
```

Optional env overrides:
- `TEST_PROJECT_ID` or `TEST_PROJECT_IDENTIFIER`
- `TEST_WP_TYPE`
- `TEST_TARGET_STATUS`

The smoke test creates a work package, updates it, verifies the result, and leaves the artifact in OpenProject because delete/archive lifecycle is not supported.

## Installation

- Base package: `pip install openproject-mcp`
- HTTP transport: `pip install "openproject-mcp[http]"`

The unified CLI is available after installation:

```bash
openproject-mcp stdio
openproject-mcp http --host 0.0.0.0 --port 8000
```

Config precedence for the CLI:
1. CLI flags
2. `FASTMCP_HOST` / `FASTMCP_PORT` and logging env vars
3. TOML config file passed with `--config`
4. Built-in defaults

See `docs/transport.md`, `docs/context.md`, and `docs/ops.md` for transport defaults, request context rules, and readiness behavior.
