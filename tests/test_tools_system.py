import pytest
import respx
from httpx import Response
from openproject_mcp.client import OpenProjectClient
from openproject_mcp.tools.system import system_ping


@pytest.fixture
def client():
    return OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")


@pytest.mark.asyncio
@respx.mock
async def test_system_ping_success(client):
    respx.get("https://mock-op.com/api/v3/users/me").mock(
        return_value=Response(200, json={"id": 5, "name": "Admin User"})
    )

    async with client:
        result = await system_ping(client)

    assert result["status"] == "ok"
    assert result["user_name"] == "Admin User"
    assert isinstance(result["latency_ms"], (int, float))
    assert result["instance_url"] == "https://mock-op.com"
