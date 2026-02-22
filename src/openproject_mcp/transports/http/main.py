from __future__ import annotations

import uvicorn

from openproject_mcp.core.logging import setup_logging

from .app import build_http_app
from .config import HttpConfig


def main() -> None:
    setup_logging()
    cfg = HttpConfig.from_env()
    app = build_http_app(cfg)
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="info")


if __name__ == "__main__":
    main()
