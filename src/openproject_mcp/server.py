from __future__ import annotations

import asyncio
import logging

from mcp.server.fastmcp import FastMCP
from mcp.server.stdio import stdio_server

from openproject_mcp.client import OpenProjectClient
from openproject_mcp.server_registry import register_discovered_tools


def create_client_from_env() -> OpenProjectClient:
    try:
        return OpenProjectClient.from_env()
    except ValueError as exc:
        raise ValueError(
            "Missing OPENPROJECT_BASE_URL or OPENPROJECT_API_KEY in environment."
        ) from exc


# --- Entry point ----------------------------------------------------------- #


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    client = create_client_from_env()

    app = FastMCP("openproject-mcp")
    register_discovered_tools(app, client)

    await stdio_server(app)


if __name__ == "__main__":
    asyncio.run(main())
