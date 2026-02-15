from __future__ import annotations

import asyncio
import logging

from .app import build_fastmcp
from .config import HttpConfig


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    cfg = HttpConfig.from_env()
    fastmcp = build_fastmcp(cfg)
    await fastmcp.run_streamable_http_async()


if __name__ == "__main__":
    asyncio.run(main())
