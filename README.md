# openproject-mcp
Small-surface MCP server for OpenProject.

It gives MCP clients a stable way to read and update a single OpenProject deployment without custom integration glue. The 1.0 line is intentionally narrow: Python 3.13, stdio and HTTP transports, deployment-fixed `OPENPROJECT_BASE_URL`, and API-key-only authentication.

## What This Server Can Do

Use this server when you want MCP clients to work with real OpenProject data and actions instead of a thin custom wrapper around the REST API.

- expose OpenProject to MCP clients over `stdio` or HTTP
- browse projects, work packages, users, memberships, and saved queries
- resolve names to IDs for projects, users, statuses, types, and priorities
- create and update work packages, add comments, attach and download files, and log time
- keep write behavior simple: any valid API key can call write tools, and OpenProject itself decides whether the key has permission

| Area | Capabilities |
|------|--------------|
| system | connectivity / ping |
| projects | list projects, get project summary |
| work packages | list, get, create, update, comment |
| users | list users, get user |
| memberships | project memberships |
| queries | list queries, run query |
| metadata | statuses, types, priorities, ID/name resolution |
| attachments | list, download, attach |
| time entries | list logged time, get my logged time, log time |

## What It Does Not Do

This project is intentionally narrow and intentionally single-tenant. It does not try to be a general auth broker, token store, or multi-tenant OpenProject gateway.

- OAuth or JWT authentication
- linked-token storage
- token-linking or link/unlink flows
- Firestore token backends
- multi-user auth flows
- per-request base URL override
- delete or archive lifecycle

For 1.0 migrations:
- the canonical HTTP auth header is `X-OpenProject-Key`
- `X-API-Key` and `Authorization: Bearer <api-key>` are accepted only as 1.x compatibility aliases
- write permission is decided by OpenProject itself, not by local scope logic

## Quickstart

Install the HTTP transport, set the OpenProject base URL in the environment, start the server with the CLI, and send requests with `X-OpenProject-Key`.

```bash
pip install "openproject-mcp[http]"

export OPENPROJECT_BASE_URL="https://your-op.example.com"
openproject-mcp http
```

```bash
curl -X POST http://127.0.0.1:8000/mcp \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'X-OpenProject-Key: your-api-key' \
  -d '{"jsonrpc":"2.0","id":"1","method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0.0.0"}}}'
```

## 1.0 Contract

### Supported

- Python: 3.13
- Transports: stdio and HTTP
- Base URL source: `OPENPROJECT_BASE_URL` from environment only
- Authentication: OpenProject API key only
- Canonical HTTP auth header: `X-OpenProject-Key`
- Compatibility aliases for 1.x: `X-API-Key`, `Authorization: Bearer <api-key>`
- Write tools run with any valid API key; OpenProject decides permission
- Health endpoints: `GET /healthz`, `GET /readyz`

### Run Modes

- HTTP: `openproject-mcp http`
- Stdio: `openproject-mcp stdio`

### Notes

- `OPENPROJECT_API_KEY` may be supplied from the environment as a default credential.
- HTTP examples and docs use `X-OpenProject-Key`.
- Per-request base URL override is not supported.
- HTTP defaults to `127.0.0.1:8000`; override with `FASTMCP_HOST`, `FASTMCP_PORT`, or CLI flags.

## Support and Validation

| Component | Supported in 1.0.0 | Validation |
|-----------|--------------------|------------|
| Python | 3.13 | CI and release checks |
| OpenProject | exact versions published at release time | `initialize` + `python -m scripts.smoke_test` against a real instance |

Exact tested OpenProject versions are recorded in `docs/release.md` before tagging `1.0.0`.

Real-instance smoke test:

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

## Detailed Docs

- Transport defaults and runtime options: `docs/transport.md`
- Request context, header precedence, and error contract: `docs/context.md`
- Health and readiness behavior: `docs/ops.md`
- Release checklist and exact tested versions: `docs/release.md`
