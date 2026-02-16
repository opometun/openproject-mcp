from __future__ import annotations

import asyncio

from mcp.server.fastmcp import FastMCP

from openproject_mcp.core.config import create_client_from_env
from openproject_mcp.core.logging import setup_logging
from openproject_mcp.core.registry import register_discovered_tools


async def main() -> None:
    setup_logging()
    client = create_client_from_env()

    app = FastMCP("openproject-mcp")
    register_discovered_tools(app, client)

    await app.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
