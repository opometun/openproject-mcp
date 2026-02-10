import pytest
import respx
from httpx import Response
from openproject_mcp.client import (
    OpenProjectClient,
    OpenProjectClientError,
    OpenProjectHTTPError,
)
from openproject_mcp.tools.attachments import attach_file_to_wp, list_attachments


@pytest.fixture
def client(tmp_path):
    f = tmp_path / "hello.txt"
    f.write_text("hi")
    return OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key"), f


@pytest.mark.asyncio
@respx.mock
async def test_attach_file_to_wp_success(client):
    cl, f = client
    route = respx.post("https://mock-op.com/api/v3/work_packages/42/attachments").mock(
        return_value=Response(
            201, json={"_type": "Attachment", "fileName": "custom.txt"}
        )
    )

    async with cl:
        resp = await attach_file_to_wp(
            cl, 42, str(f), description="desc", file_name="custom.txt"
        )

    assert resp["fileName"] == "custom.txt"
    req = route.calls[0].request
    assert "multipart/form-data" in req.headers["Content-Type"]
    # metadata part should carry fileName override as a field, not a file
    assert b'{"fileName": "custom.txt", "description": "desc"}' in req.content


@pytest.mark.asyncio
async def test_attach_file_missing_raises(tmp_path):
    cl = OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")
    missing = tmp_path / "nope.bin"
    async with cl:
        with pytest.raises(OpenProjectClientError):
            await attach_file_to_wp(cl, 1, str(missing))


@pytest.mark.asyncio
@respx.mock
async def test_attach_file_non_2xx_raises(client):
    cl, f = client
    respx.post("https://mock-op.com/api/v3/work_packages/42/attachments").mock(
        return_value=Response(422, json={"message": "Invalid"})
    )

    async with cl:
        with pytest.raises(OpenProjectHTTPError):
            await attach_file_to_wp(cl, 42, str(f))


@pytest.mark.asyncio
@respx.mock
async def test_attach_file_with_content_base64(client):
    cl, f = client
    route = respx.post("https://mock-op.com/api/v3/work_packages/42/attachments").mock(
        return_value=Response(
            201, json={"_type": "Attachment", "fileName": "inline.bin"}
        )
    )

    b64 = "aGVsbG8="  # "hello"
    async with cl:
        resp = await attach_file_to_wp(
            cl,
            42,
            file_path=None,
            content_base64=b64,
            file_name="inline.bin",
        )

    assert resp["fileName"] == "inline.bin"
    req = route.calls[0].request
    assert "multipart/form-data" in req.headers["Content-Type"]


@pytest.mark.asyncio
async def test_attach_file_empty_content_rejected():
    cl = OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")
    async with cl:
        with pytest.raises(OpenProjectClientError):
            await attach_file_to_wp(cl, 1, content=b"", file_name="empty.txt")


@pytest.mark.asyncio
@respx.mock
async def test_list_attachments_success(client):
    cl, f = client
    respx.get("https://mock-op.com/api/v3/work_packages/42/attachments").mock(
        return_value=Response(
            200,
            json={
                "total": 1,
                "_embedded": {
                    "elements": [
                        {
                            "id": 9,
                            "fileName": "doc.txt",
                            "fileSize": 123,
                            "_links": {
                                "downloadLocation": {
                                    "href": "/api/v3/attachments/9/download"
                                }
                            },
                        }
                    ]
                },
            },
        )
    )

    async with cl:
        data = await list_attachments(cl, 42)

    item = data["items"][0]
    assert item["id"] == 9
    assert item["file_name"] == "doc.txt"
    assert item["file_size"] == 123
    assert item["download_href"].endswith("/api/v3/attachments/9/download")


@pytest.mark.asyncio
@respx.mock
async def test_list_attachments_404_propagates(client):
    cl, f = client
    respx.get("https://mock-op.com/api/v3/work_packages/42/attachments").mock(
        return_value=Response(404, json={"message": "Not found"})
    )

    async with cl:
        with pytest.raises(OpenProjectHTTPError):
            await list_attachments(cl, 42)
