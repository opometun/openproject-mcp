# 1.0 Release Checklist

Use this checklist as the go/no-go gate for tagging `1.0.0`.

## Contract Check

- [ ] README, `docs/transport.md`, `docs/context.md`, and `docs/ops.md` describe the same supported product.
- [ ] Quickstart works exactly as written on a clean install.
- [ ] `openproject-mcp http` defaults to `127.0.0.1:8000`.
- [ ] `FASTMCP_HOST` and `FASTMCP_PORT` match the documented HTTP override path.
- [ ] `X-OpenProject-Key` is the only header shown in the quickstart and main request examples.
- [ ] Compatibility aliases are documented consistently as 1.x-only compatibility behavior.
- [ ] No unsupported features are described as current behavior in the main docs.
- [ ] CI passes on the reduced 1.0 feature set.

## Release Validation

Record the exact validation results here before tagging `1.0.0`.

| Component | Versions | Validation method | Validated on |
|-----------|----------|-------------------|--------------|
| Python | 3.11, 3.13 | CI + local test suite | |
| OpenProject | | `initialize` plus `python -m scripts.smoke_test` against each claimed live version | |

`1.0.0` is blocked until the OpenProject row is filled with exact tested versions and the smoke test result is recorded.
