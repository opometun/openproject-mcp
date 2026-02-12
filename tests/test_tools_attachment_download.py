import base64
from pathlib import Path

import pytest
import respx
from httpx import Response
from openproject_mcp.client import OpenProjectClient, OpenProjectHTTPError
from openproject_mcp.tools.attachments import (
    download_attachment,
    get_attachment_content,
)


@pytest.fixture
def client(tmp_path: Path):
    return OpenProjectClient(
        base_url="https://mock-op.com", api_key="mock-key"
    ), tmp_path


@pytest.mark.asyncio
@respx.mock
async def test_download_attachment_saves_file(client):
    cl, tmp = client
    respx.get("https://mock-op.com/api/v3/attachments/9").mock(
        return_value=Response(
            200,
            json={
                "fileName": "doc.txt",
                "_links": {
                    "downloadLocation": {
                        "href": "https://mock-op.com/api/v3/attachments/9/download"
                    }
                },
            },
        )
    )
    respx.get("https://mock-op.com/api/v3/attachments/9/download").mock(
        return_value=Response(200, content=b"hello")
    )

    async with cl:
        path = await download_attachment(cl, 9, dest_path=str(tmp))

    saved = Path(path)
    assert saved.exists()
    assert saved.read_bytes() == b"hello"


@pytest.mark.asyncio
@respx.mock
async def test_get_attachment_content_preview(client):
    cl, _ = client
    respx.get("https://mock-op.com/api/v3/attachments/9").mock(
        return_value=Response(
            200,
            json={
                "fileName": "doc.txt",
                "_links": {
                    "downloadLocation": {
                        "href": "https://mock-op.com/api/v3/attachments/9/download"
                    }
                },
            },
        )
    )
    respx.get("https://mock-op.com/api/v3/attachments/9/download").mock(
        return_value=Response(
            206, headers={"Content-Type": "text/plain"}, content=b"abcdefghij"
        )
    )

    async with cl:
        preview = await get_attachment_content(cl, 9, max_bytes=5)

    assert base64.b64decode(preview["bytes"]) == b"abcde"
    assert preview["size"] == 5
    assert preview["content_type"] == "text/plain"


@pytest.mark.asyncio
@respx.mock
async def test_get_attachment_content_416_fallback(client):
    cl, _ = client
    respx.get("https://mock-op.com/api/v3/attachments/9").mock(
        return_value=Response(
            200,
            json={
                "fileName": "doc.txt",
                "_links": {
                    "downloadLocation": {
                        "href": "https://mock-op.com/api/v3/attachments/9/download"
                    }
                },
            },
        )
    )

    respx.get("https://mock-op.com/api/v3/attachments/9/download").mock(
        side_effect=[
            Response(416, json={"message": "Range Not Satisfiable"}),
            Response(
                200, headers={"Content-Type": "text/plain"}, content=b"hello world"
            ),
        ]
    )

    async with cl:
        preview = await get_attachment_content(cl, 9, max_bytes=5)

    assert base64.b64decode(preview["bytes"]) == b"hello"
    assert preview["size"] == 5


@pytest.mark.asyncio
@respx.mock
async def test_download_attachment_404_propagates(client):
    cl, tmp = client
    respx.get("https://mock-op.com/api/v3/attachments/9").mock(
        return_value=Response(404, json={"message": "Not found"})
    )

    async with cl:
        with pytest.raises(OpenProjectHTTPError):
            await download_attachment(cl, 9, dest_path=str(tmp))
