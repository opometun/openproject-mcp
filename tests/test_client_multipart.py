from pathlib import Path

import pytest
import respx
from httpx import Response
from openproject_mcp.core.client import (
    OpenProjectClient,
    OpenProjectClientError,
    OpenProjectHTTPError,
)


@pytest.fixture
def client(tmp_path: Path):
    # small temp file
    f = tmp_path / "sample.txt"
    f.write_text("hello")
    return OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key"), f


@pytest.mark.asyncio
@respx.mock
async def test_post_file_success(client):
    cl, f = client
    route = respx.post("https://mock-op.com/api/v3/attachments").mock(
        return_value=Response(201, json={"_type": "Attachment", "fileName": f.name})
    )

    async with cl:
        resp = await cl.post_file("/api/v3/attachments", file_path=str(f))

    assert resp["fileName"] == f.name
    req = route.calls[0].request
    assert "multipart/form-data" in req.headers["Content-Type"]


@pytest.mark.asyncio
@respx.mock
async def test_post_file_mime_override(client):
    cl, f = client
    route = respx.post("https://mock-op.com/api/v3/attachments").mock(
        return_value=Response(201, json={"ok": True})
    )

    async with cl:
        await cl.post_file(
            "/api/v3/attachments",
            file_path=str(f),
            content_type="application/x-custom",
        )

    req = route.calls[0].request
    # boundary in content-type; check the filename tuple encoded content type
    assert "multipart/form-data" in req.headers["Content-Type"]


@pytest.mark.asyncio
async def test_post_file_missing_file_raises(tmp_path: Path):
    cl = OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")
    missing = tmp_path / "nope.bin"
    async with cl:
        with pytest.raises(OpenProjectClientError):
            await cl.post_file("/api/v3/attachments", file_path=str(missing))


@pytest.mark.asyncio
@respx.mock
async def test_post_file_non_json_body(client):
    cl, f = client
    # Return empty body
    respx.post("https://mock-op.com/api/v3/attachments").mock(
        return_value=Response(200, content=b"")
    )

    async with cl:
        resp = await cl.post_file("/api/v3/attachments", file_path=str(f))

    assert resp == {}


@pytest.mark.asyncio
@respx.mock
async def test_post_file_non_2xx_raises(client):
    cl, f = client
    respx.post("https://mock-op.com/api/v3/attachments").mock(
        return_value=Response(422, json={"message": "Invalid"})
    )

    async with cl:
        with pytest.raises(OpenProjectHTTPError):
            await cl.post_file("/api/v3/attachments", file_path=str(f))
