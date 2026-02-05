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
