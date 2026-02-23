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
