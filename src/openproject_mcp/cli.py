from __future__ import annotations

import argparse
import asyncio
import os
import tomllib
from dataclasses import dataclass, replace
from typing import Any, Dict, Optional

from openproject_mcp.core.logging import setup_logging

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
DEFAULT_LOG_LEVEL = "info"


@dataclass(frozen=True)
class CliConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    log_level: str = DEFAULT_LOG_LEVEL


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openproject-mcp", description="Unified CLI for OpenProject MCP server"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", help="Path to TOML config file", default=None)
    common.add_argument(
        "--log-level", help="Logging level (debug, info, warning, error)", default=None
    )

    subparsers.add_parser("stdio", parents=[common], help="Run MCP over stdio")

    http = subparsers.add_parser("http", parents=[common], help="Run MCP over HTTP")
    http.add_argument("--host", help="HTTP host (default 127.0.0.1)", default=None)
    http.add_argument("--port", type=int, help="HTTP port (default 8080)", default=None)

    return parser


def _load_config_file(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    with open(path, "rb") as f:
        data = tomllib.load(f)
    # Accept top-level keys host/port/log_level
    return {
        "host": data.get("host"),
        "port": data.get("port"),
        "log_level": data.get("log_level"),
    }


def merge_config(args: argparse.Namespace) -> CliConfig:
    file_cfg = _load_config_file(args.config)

    # Base defaults
    cfg = CliConfig()

    # Config file (if present)
    if file_cfg.get("host"):
        cfg = replace(cfg, host=str(file_cfg["host"]))
    if file_cfg.get("port"):
        cfg = replace(cfg, port=int(file_cfg["port"]))
    if file_cfg.get("log_level"):
        cfg = replace(cfg, log_level=str(file_cfg["log_level"]))

    # Environment overrides
    env_host = os.getenv("MCP_HTTP_HOST")
    env_port = os.getenv("MCP_HTTP_PORT")
    env_log = os.getenv("MCP_LOG_LEVEL") or os.getenv("OPENPROJECT_LOG_LEVEL")
    if env_host:
        cfg = replace(cfg, host=env_host)
    if env_port:
        cfg = replace(cfg, port=int(env_port))
    if env_log:
        cfg = replace(cfg, log_level=env_log)

    # CLI overrides (highest precedence)
    if getattr(args, "host", None):
        cfg = replace(cfg, host=args.host)
    if getattr(args, "port", None):
        cfg = replace(cfg, port=args.port)
    if getattr(args, "log_level", None):
        cfg = replace(cfg, log_level=args.log_level)

    return cfg


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = merge_config(args)

    # Transport-aware logging: always stderr, level from merged config
    setup_logging(cfg.log_level.upper())

    if args.command == "stdio":
        from openproject_mcp.transports.stdio.main import run_stdio

        asyncio.run(run_stdio())
    elif args.command == "http":
        try:
            from openproject_mcp.transports.http.main import run_http
        except ImportError:
            raise SystemExit(  # noqa: B904
                "HTTP transport requires extra dependencies.\n"
                "Install with: pip install 'openproject-mcp[http]'"
            )
        run_http(cfg.host, cfg.port)
    else:  # pragma: no cover - argparse enforces choices
        parser.error(f"Unknown command {args.command}")


if __name__ == "__main__":
    main()
