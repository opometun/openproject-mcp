import pytest
import respx
from httpx import Response
from openproject_mcp.core.client import OpenProjectClient
from openproject_mcp.core.tools import metadata
from openproject_mcp.core.tools.metadata import (
    AmbiguousResolutionError,
    NotFoundResolutionError,
    resolve_project,
    resolve_user,
)


@pytest.fixture(autouse=True)
def clear_cache():
    metadata._CACHE.clear()
    yield
    metadata._CACHE.clear()


@pytest.fixture
def client():
    return OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")


@pytest.mark.asyncio
@respx.mock
async def test_resolve_project_identifier_exact(client):
    respx.get("https://mock-op.com/api/v3/projects").mock(
        return_value=Response(
            200,
            json={
                "_embedded": {
                    "elements": [
                        {"id": 1, "name": "Demo Project", "identifier": "demo"},
                    ]
                }
            },
        )
    )

    async with client:
        pid = await resolve_project(client, "demo")

    assert pid == 1


@pytest.mark.asyncio
@respx.mock
async def test_resolve_project_ambiguous(client):
    respx.get("https://mock-op.com/api/v3/projects").mock(
        return_value=Response(
            200,
            json={
                "_embedded": {
                    "elements": [
                        {"id": 1, "name": "Alpha Demo", "identifier": "alpha"},
                        {"id": 2, "name": "Beta Demo", "identifier": "beta"},
                    ]
                }
            },
        )
    )

    async with client:
        with pytest.raises(AmbiguousResolutionError) as exc:
            await resolve_project(client, "demo")

    assert "Alpha Demo" in str(exc.value)
    assert "Beta Demo" in str(exc.value)


@pytest.mark.asyncio
@respx.mock
async def test_resolve_project_multi_page(client):
    def responder(request):
        offset = int(request.url.params.get("offset", 0))
        if offset == 0:
            return Response(
                200,
                json={
                    "_embedded": {
                        "elements": [{"id": 1, "name": "Alpha", "identifier": "alpha"}]
                    },
                },
            )
        return Response(
            200,
            json={
                "_embedded": {
                    "elements": [{"id": 5, "name": "Target", "identifier": "target"}]
                },
            },
        )

    respx.get("https://mock-op.com/api/v3/projects").mock(side_effect=responder)

    async with client:
        pid = await resolve_project(client, "target", max_pages=2)

    assert pid == 5


@pytest.mark.asyncio
@respx.mock
async def test_resolve_project_not_found(client):
    respx.get("https://mock-op.com/api/v3/projects").mock(
        return_value=Response(
            200,
            json={
                "_embedded": {
                    "elements": [{"id": 1, "name": "Alpha", "identifier": "alpha"}]
                },
            },
        )
    )

    async with client:
        with pytest.raises(NotFoundResolutionError):
            await resolve_project(client, "missing")


@pytest.mark.asyncio
@respx.mock
async def test_resolve_user_exact(client):
    respx.get("https://mock-op.com/api/v3/users").mock(
        return_value=Response(
            200,
            json={
                "_embedded": {
                    "elements": [
                        {"id": 7, "name": "Ada Lovelace", "login": "ada"},
                    ]
                }
            },
        )
    )

    async with client:
        uid = await resolve_user(client, "Ada Lovelace")

    assert uid == 7


@pytest.mark.asyncio
@respx.mock
async def test_resolve_user_ambiguous(client):
    respx.get("https://mock-op.com/api/v3/users").mock(
        return_value=Response(
            200,
            json={
                "_embedded": {
                    "elements": [
                        {"id": 1, "name": "Jane Doe", "login": "jane"},
                        {"id": 2, "name": "Jane Smith", "login": "jane.s"},
                    ]
                }
            },
        )
    )

    async with client:
        with pytest.raises(AmbiguousResolutionError):
            await resolve_user(client, "jane")


@pytest.mark.asyncio
@respx.mock
async def test_resolve_user_permission_error(client):
    respx.get("https://mock-op.com/api/v3/users").mock(
        return_value=Response(403, json={"message": "forbidden"})
    )

    async with client:
        with pytest.raises(metadata.ResolutionError):
            await resolve_user(client, "any")
