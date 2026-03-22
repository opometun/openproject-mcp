# 1.0 Release Checklist

Use this checklist as the go/no-go gate for tagging `1.0.0`.

## Contract Check

- [x] README, `docs/transport.md`, `docs/context.md`, and `docs/ops.md` describe the same supported product.
- [x] Quickstart works exactly as written on a clean install.
- [x] `openproject-mcp http` defaults to `127.0.0.1:8000`.
- [x] `FASTMCP_HOST` and `FASTMCP_PORT` match the documented HTTP override path.
- [x] `X-OpenProject-Key` is the only header shown in the quickstart and main request examples.
- [x] Compatibility aliases are documented consistently as 1.x-only compatibility behavior.
- [x] No unsupported features are described as current behavior in the main docs.
- [x] CI passes on the reduced 1.0 feature set.

## Release Validation

Record the exact validation results here before tagging `1.0.0`.

| Component | Versions | Validation method | Validated on |
|-----------|----------|-------------------|--------------|
| Python | 3.13 | `ruff check .`, `ruff format --check .`, `pytest`, and base-install CLI help checks | 2026-03-22 |
| OpenProject | Pending live validation before tag | `initialize` plus `python -m scripts.smoke_test` against each claimed live version | |

Notes:
- A local `initialize` request against the HTTP runner succeeded on 2026-03-22 using the documented `X-OpenProject-Key` header and default `127.0.0.1:8000` bind.
- The README quickstart was validated on 2026-03-22 against a clean ephemeral `.[http]` install using `openproject-mcp http`.
- Bump `pyproject.toml` to `version = "1.0.0"` only in the final release-prep commit, after the exact tested OpenProject version(s) are recorded below.
- The remaining release blocker is live OpenProject validation from a real instance so the exact tested OpenProject version(s) can be published truthfully.

`1.0.0` is blocked until the OpenProject row is filled with exact tested versions and the smoke test result is recorded.
