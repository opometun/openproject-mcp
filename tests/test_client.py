import base64

import httpx
import pytest
import respx
from httpx import Response
from openproject_mcp.core.client import (
    OpenProjectClient,
    OpenProjectClientError,
    OpenProjectHTTPError,
    OpenProjectParseError,
)


@pytest.mark.asyncio
async def test_get_request_success():
    async with respx.mock:
        route = respx.get("https://mock-op.com/api/v3/projects").mock(
            return_value=Response(200, json={"_type": "Collection", "total": 5})
        )

        client = OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")
        async with client:
            data = await client.get("/api/v3/projects")
            assert data["_type"] == "Collection"
            assert data["total"] == 5

        assert route.called


@pytest.mark.asyncio
async def test_auth_header_is_basic_apikey():
    async with respx.mock:
        route = respx.get("https://mock-op.com/api/v3/projects").mock(
            return_value=Response(200, json={"_type": "Collection", "total": 0})
        )

        client = OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")
        async with client:
            await client.get("/api/v3/projects")

        # httpx.BasicAuth automatically encodes credentials
        sent = route.calls[0].request.headers
        expected = "Basic " + base64.b64encode(b"apikey:mock-key").decode()

        assert sent.get("Authorization") == expected


@pytest.mark.asyncio
async def test_404_raises_typed_error():
    async with respx.mock:
        respx.get("https://mock-op.com/api/v3/projects/999").mock(
            return_value=Response(404, json={"message": "Not found"})
        )

        client = OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")
        async with client:
            with pytest.raises(OpenProjectHTTPError) as exc:
                await client.get("/api/v3/projects/999")

        assert exc.value.status_code == 404
        assert "Not found" in str(exc.value)


@pytest.mark.asyncio
async def test_401_raises_typed_error():
    async with respx.mock:
        respx.get("https://mock-op.com/api/v3/projects").mock(
            return_value=Response(401, json={"message": "Unauthorized"})
        )

        client = OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")
        async with client:
            with pytest.raises(OpenProjectHTTPError) as exc:
                await client.get("/api/v3/projects")

        assert exc.value.status_code == 401
        assert "Unauthorized" in str(exc.value)


@pytest.mark.asyncio
async def test_422_raises_typed_error():
    async with respx.mock:
        respx.post("https://mock-op.com/api/v3/projects").mock(
            return_value=Response(422, json={"message": "Invalid data"})
        )

        client = OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")
        async with client:
            with pytest.raises(OpenProjectHTTPError) as exc:
                await client.post("/api/v3/projects", json={"name": ""})

        assert exc.value.status_code == 422
        assert "Invalid data" in str(exc.value)


@pytest.mark.asyncio
async def test_connect_timeout_after_retries():
    async with respx.mock:
        respx.get("https://mock-op.com/api/v3/projects").mock(
            side_effect=httpx.ConnectTimeout("boom")
        )

        client = OpenProjectClient(
            base_url="https://mock-op.com", api_key="mock-key", timeout_seconds=0.1
        )
        async with client:
            with pytest.raises(OpenProjectClientError):
                await client.get("/api/v3/projects")


@pytest.mark.asyncio
async def test_empty_response_returns_empty_dict():
    """Test that 204 No Content or empty responses return {}"""
    async with respx.mock:
        respx.get("https://mock-op.com/api/v3/some-endpoint").mock(
            return_value=Response(204)
        )

        client = OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")
        async with client:
            data = await client.get("/api/v3/some-endpoint")
            assert data == {}


@pytest.mark.asyncio
async def test_non_json_response_raises_parse_error():
    """Test that non-JSON responses raise OpenProjectParseError"""
    async with respx.mock:
        respx.get("https://mock-op.com/api/v3/projects").mock(
            return_value=Response(200, text="<html>Not JSON</html>")
        )

        client = OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")
        async with client:
            with pytest.raises(OpenProjectParseError) as exc:
                await client.get("/api/v3/projects")

            assert "Expected JSON" in str(exc.value)


@pytest.mark.asyncio
async def test_retries_on_503():
    """Test that 503 errors are retried according to RetryConfig"""
    async with respx.mock:
        route = respx.get("https://mock-op.com/api/v3/projects").mock(
            side_effect=[
                Response(503, json={"message": "Service Unavailable"}),
                Response(503, json={"message": "Service Unavailable"}),
                Response(200, json={"_type": "Collection", "total": 1}),
            ]
        )

        client = OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")
        async with client:
            data = await client.get("/api/v3/projects")
            assert data["total"] == 1

        # Should have been called 3 times (initial + 2 retries)
        assert route.call_count == 3
