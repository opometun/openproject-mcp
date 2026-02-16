from __future__ import annotations

import asyncio

from mcp.server.fastmcp import FastMCP

from openproject_mcp.core.context import (
    apply_request_context,
    client_from_context,
    reset_context,
    seed_from_env,
)
from openproject_mcp.core.logging import setup_logging
from openproject_mcp.core.registry import register_discovered_tools


async def main() -> None:
    setup_logging()
    # Seed ContextVars from env (stdio bootstrap)
    ctx = seed_from_env(use_dotenv=True)
    tokens = list(
        apply_request_context(
            api_key=ctx.api_key,
            base_url=ctx.base_url,
            request_id=ctx.request_id,
            user_agent=ctx.user_agent,
        )
    )
    client = client_from_context()

    app = FastMCP("openproject-mcp")
    register_discovered_tools(app, lambda: client)

    await app.run_stdio_async()
    reset_context(tokens)


if __name__ == "__main__":
    asyncio.run(main())
