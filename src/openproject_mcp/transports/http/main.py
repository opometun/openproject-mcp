from __future__ import annotations

from dataclasses import replace


def run_http(host: str | None = None, port: int | None = None) -> None:
    try:
        import uvicorn  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "HTTP transport requires extra dependencies. "
            "Install with: pip install 'openproject-mcp[http]'"
        ) from exc

    from .app import build_http_app
    from .config import HttpConfig

    cfg = HttpConfig.from_env()
    if host or port:
        cfg = replace(cfg, host=host or cfg.host, port=port or cfg.port)
    app = build_http_app(cfg)
    uvicorn.run(
        app,
        host=cfg.host,
        port=cfg.port,
        log_level="info",
        timeout_graceful_shutdown=10,
    )


def main() -> None:
    from openproject_mcp.core.logging import setup_logging

    setup_logging()
    run_http()


if __name__ == "__main__":
    main()
