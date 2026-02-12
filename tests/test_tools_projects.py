import pytest
import respx
from httpx import Response
from openproject_mcp.client import OpenProjectClient, OpenProjectHTTPError
from openproject_mcp.tools.projects import get_project_summary, list_projects

PROJECTS_PAYLOAD = {
    "_type": "Collection",
    "total": 3,
    "_embedded": {
        "elements": [
            {"id": 1, "name": "Alpha", "identifier": "alpha"},
            {"id": 2, "name": "Beta", "identifier": "beta"},
        ]
    },
}


@pytest.fixture
def client():
    return OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")


@pytest.mark.asyncio
@respx.mock
async def test_list_projects_returns_items_and_paging(client):
    payload = {
        "_type": "Collection",
        "total": 120,
        "_embedded": {
            "elements": [
                {"id": 1, "name": "Alpha"},
                {"id": 2, "name": "Beta"},
            ]
        },
    }
    respx.get("https://mock-op.com/api/v3/projects").mock(
        return_value=Response(200, json=payload)
    )

    async with client:
        result = await list_projects(client)

    assert result["items"] == [
        {"id": 1, "name": "Alpha", "identifier": None},
        {"id": 2, "name": "Beta", "identifier": None},
    ]
    assert result["offset"] == 0
    assert result["page_size"] == 50
    assert result["total"] == 120
    assert result["next_offset"] == 50  # more data implied by total


@pytest.mark.asyncio
@respx.mock
async def test_pagination_params_sent(client):
    route = respx.get("https://mock-op.com/api/v3/projects").mock(
        return_value=Response(200, json=PROJECTS_PAYLOAD)
    )

    async with client:
        await list_projects(client, offset=20, page_size=10)

    request = route.calls[0].request
    assert request.url.params["offset"] == "20"
    assert request.url.params["pageSize"] == "10"


@pytest.mark.asyncio
@respx.mock
async def test_next_offset_none_at_end(client):
    payload = {
        "_type": "Collection",
        "total": 2,
        "_embedded": {
            "elements": [
                {"id": 1, "name": "Alpha", "identifier": "alpha"},
                {"id": 2, "name": "Beta", "identifier": "beta"},
            ]
        },
    }
    respx.get("https://mock-op.com/api/v3/projects").mock(
        return_value=Response(200, json=payload)
    )

    async with client:
        result = await list_projects(client, offset=0, page_size=2)

    assert result["next_offset"] is None
    assert result["items"][0]["identifier"] == "alpha"


@pytest.mark.asyncio
@respx.mock
async def test_name_contains_filters_client_side(client):
    respx.get("https://mock-op.com/api/v3/projects").mock(
        return_value=Response(200, json=PROJECTS_PAYLOAD)
    )

    async with client:
        result = await list_projects(client, name_contains="alp")

    assert result["items"] == [{"id": 1, "name": "Alpha", "identifier": "alpha"}]
    # total remains based on payload (3), even though items filtered client-side
    assert result["total"] == 3


@pytest.mark.asyncio
async def test_negative_offset_raises():
    client = OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")
    async with client:
        with pytest.raises(ValueError):
            await list_projects(client, offset=-1)


@pytest.mark.asyncio
@respx.mock
async def test_page_size_clamped(client):
    route = respx.get("https://mock-op.com/api/v3/projects").mock(
        return_value=Response(200, json=PROJECTS_PAYLOAD)
    )

    async with client:
        await list_projects(client, page_size=500)

    request = route.calls[0].request
    assert request.url.params["pageSize"] == "200"


@pytest.mark.asyncio
@respx.mock
async def test_list_projects_404_propagates(client):
    respx.get("https://mock-op.com/api/v3/projects").mock(
        return_value=Response(404, json={"message": "Not found"})
    )

    async with client:
        with pytest.raises(OpenProjectHTTPError):
            await list_projects(client)


@pytest.mark.asyncio
@respx.mock
async def test_get_project_summary_happy_path(client):
    respx.get("https://mock-op.com/api/v3/projects/5").mock(
        return_value=Response(
            200,
            json={
                "id": 5,
                "name": "Demo",
                "identifier": "demo",
                "active": True,
                "description": {"raw": "Hello"},
            },
        )
    )
    respx.get("https://mock-op.com/api/v3/work_packages").mock(
        return_value=Response(
            200,
            json={
                "total": 10,
                "_embedded": {"elements": []},
            },
        )
    )
    respx.get("https://mock-op.com/api/v3/projects/5/versions").mock(
        return_value=Response(
            200,
            json={
                "_embedded": {
                    "elements": [
                        {"id": 21, "name": "v1"},
                        {"id": 22, "name": "v2"},
                    ]
                },
                "total": 2,
            },
        )
    )
    respx.get("https://mock-op.com/api/v3/memberships").mock(
        return_value=Response(
            200,
            json={
                "_embedded": {
                    "elements": [
                        {
                            "_links": {
                                "principal": {
                                    "href": "/api/v3/users/9",
                                    "title": "Bob",
                                },
                            },
                            "_embedded": {"roles": [{"name": "Dev"}]},
                        },
                        {
                            "_links": {
                                "principal": {
                                    "href": "/api/v3/users/10",
                                    "title": "Ann",
                                },
                            },
                            "_embedded": {"roles": [{"name": "QA"}]},
                        },
                    ]
                }
            },
        )
    )

    async with client:
        summary = await get_project_summary(client, 5)

    assert summary["project"]["id"] == 5
    assert summary["work_packages"]["total"] == 10
    assert summary["versions"]["total"] == 2
    assert summary["members"]["total"] == 2
    assert summary["members"]["roles"]["Dev"] == 1
