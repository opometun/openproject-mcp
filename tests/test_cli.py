import os

from openproject_mcp import cli


def test_merge_precedence_cli_over_env_over_file(monkeypatch, tmp_path):
    # config file baseline
    cfg_file = tmp_path / "cfg.toml"
    cfg_file.write_text('host = "10.0.0.1"\nport = 9999\nlog_level = "warning"\n')

    # env overrides file
    monkeypatch.setenv("MCP_HTTP_HOST", "10.0.0.2")
    monkeypatch.setenv("MCP_HTTP_PORT", "7777")
    monkeypatch.setenv("MCP_LOG_LEVEL", "error")

    parser = cli.build_parser()
    args = parser.parse_args(["http", "--config", str(cfg_file), "--host", "0.0.0.0"])
    merged = cli.merge_config(args)

    # CLI wins for host
    assert merged.host == "0.0.0.0"
    # Env wins over file for port/log_level
    assert merged.port == 7777
    assert merged.log_level == "error"


def test_default_values_when_no_overrides():
    parser = cli.build_parser()
    args = parser.parse_args(["http"])
    merged = cli.merge_config(args)
    assert merged.host == cli.DEFAULT_HOST
    assert merged.port == cli.DEFAULT_PORT
    assert merged.log_level == cli.DEFAULT_LOG_LEVEL


def test_cli_importable_without_http_extra(tmp_path):
    """cli.py must be importable even when starlette/uvicorn are absent.

    NOTE: As of mcp>=1.11, starlette and uvicorn are core transitive deps of
    the ``mcp`` package, so this scenario cannot actually occur in practice.
    We keep the test as a guard in case upstream changes.
    """
    # Verify the module-level import chain does NOT pull starlette eagerly.
    # We can't truly hide starlette (mcp itself imports it), but we verify
    # that cli.py itself does not import from the http transport at the top
    # level — only in the 'http' command branch.
    import ast

    cli_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "src",
        "openproject_mcp",
        "cli.py",
    )
    with open(cli_path) as f:
        tree = ast.parse(f.read())

    top_level_imports: list[str] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            top_level_imports.append(node.module)

    # cli.py must NOT eagerly import the http transport at the top level
    assert not any("transports.http" in m for m in top_level_imports), (
        "cli.py has a top-level import from transports.http — "
        "this would break a hypothetical base-only install"
    )
