import pytest
import respx
from httpx import Response
from openproject_mcp.client import OpenProjectClient
from openproject_mcp.tools import metadata
from openproject_mcp.tools.metadata import (
    list_priorities,
    list_statuses,
    list_types,
    resolve_priority_id,
    resolve_status_id,
    resolve_type_id,
)

TYPES_PAYLOAD = {
    "_type": "Collection",
    "_embedded": {
        "elements": [
            {"id": 1, "name": "Bug"},
            {"id": 2, "name": "Task"},
        ]
    },
}

STATUSES_PAYLOAD = {
    "_type": "Collection",
    "_embedded": {
        "elements": [
            {"id": 1, "name": "New", "isClosed": False},
            {"id": 2, "name": "Closed", "isClosed": True},
        ]
    },
}

PRIORITIES_PAYLOAD = {
    "_type": "Collection",
    "_embedded": {
        "elements": [
            {"id": 5, "name": "Normal"},
            {"id": 6, "name": "High"},
        ]
    },
}


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
async def test_list_types_returns_minimal_json(client):
    respx.get("https://mock-op.com/api/v3/types").mock(
        return_value=Response(200, json=TYPES_PAYLOAD)
    )

    async with client:
        data = await list_types(client)

    assert data == [{"id": 1, "name": "Bug"}, {"id": 2, "name": "Task"}]


@pytest.mark.asyncio
@respx.mock
async def test_list_statuses_returns_is_closed(client):
    respx.get("https://mock-op.com/api/v3/statuses").mock(
        return_value=Response(200, json=STATUSES_PAYLOAD)
    )

    async with client:
        data = await list_statuses(client)

    assert data == [
        {"id": 1, "name": "New", "is_closed": False},
        {"id": 2, "name": "Closed", "is_closed": True},
    ]


@pytest.mark.asyncio
@respx.mock
async def test_list_priorities_returns_minimal_json(client):
    respx.get("https://mock-op.com/api/v3/priorities").mock(
        return_value=Response(200, json=PRIORITIES_PAYLOAD)
    )

    async with client:
        data = await list_priorities(client)

    assert data == [{"id": 5, "name": "Normal"}, {"id": 6, "name": "High"}]


@pytest.mark.asyncio
@respx.mock
async def test_resolve_type_id_case_insensitive(client):
    respx.get("https://mock-op.com/api/v3/types").mock(
        return_value=Response(200, json=TYPES_PAYLOAD)
    )

    async with client:
        assert await resolve_type_id(client, "bug") == 1
        assert await resolve_type_id(client, "BUG") == 1


@pytest.mark.asyncio
@respx.mock
async def test_resolve_status_id_substring_fallback(client):
    respx.get("https://mock-op.com/api/v3/statuses").mock(
        return_value=Response(200, json=STATUSES_PAYLOAD)
    )

    async with client:
        assert await resolve_status_id(client, "Clos") == 2


@pytest.mark.asyncio
@respx.mock
async def test_resolve_priority_id_not_found_lists_available(client):
    respx.get("https://mock-op.com/api/v3/priorities").mock(
        return_value=Response(200, json=PRIORITIES_PAYLOAD)
    )

    async with client:
        with pytest.raises(ValueError) as exc:
            await resolve_priority_id(client, "Urgent")

    assert "Available" in str(exc.value)
    assert "Normal" in str(exc.value)


@pytest.mark.asyncio
@respx.mock
async def test_list_types_uses_cache(client):
    route = respx.get("https://mock-op.com/api/v3/types").mock(
        return_value=Response(200, json=TYPES_PAYLOAD)
    )

    async with client:
        await list_types(client)
        await list_types(client)

    assert route.call_count == 1
