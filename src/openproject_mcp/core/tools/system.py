import time

from openproject_mcp.core.client import OpenProjectClient


async def system_ping(client: OpenProjectClient) -> dict:
    """
    Simple connectivity and latency check against the OpenProject instance.
    Returns status plus the authenticated user's name and id.
    """
    start = time.perf_counter()

    user_data = await client.get("/api/v3/users/me", tool="system_ping")

    latency_ms = (time.perf_counter() - start) * 1000

    return {
        "status": "ok",
        "latency_ms": round(latency_ms, 2),
        "user_name": user_data.get("name", "Unknown"),
        "user_id": user_data.get("id"),
        "instance_url": client.base_url,
    }
