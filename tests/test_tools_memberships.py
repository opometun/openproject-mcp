import pytest
import respx
from httpx import Response
from openproject_mcp.client import OpenProjectClient, OpenProjectHTTPError
from openproject_mcp.tools.memberships import get_project_memberships


@pytest.fixture
def client():
    return OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")


@pytest.mark.asyncio
@respx.mock
async def test_get_project_memberships_single_page(client):
    respx.get("https://mock-op.com/api/v3/projects", params={"pageSize": "200"}).mock(
        return_value=Response(
            200,
            json={
                "_embedded": {
                    "elements": [
                        {"id": 5, "name": "Demo", "identifier": "demo"},
                    ]
                }
            },
        )
    )

    respx.get("https://mock-op.com/api/v3/memberships").mock(
        return_value=Response(
            200,
            json={
                "total": 1,
                "_embedded": {
                    "elements": [
                        {
                            "id": 10,
                            "_embedded": {
                                "user": {"id": 7, "name": "Ada"},
                                "roles": [{"id": 2, "name": "Developer"}],
                            },
                        }
                    ]
                },
            },
        )
    )

    async with client:
        data = await get_project_memberships(client, "demo")

    assert data["items"][0]["principal_name"] == "Ada"
    assert data["items"][0]["roles"] == ["Developer"]
    assert data["items"][0]["membership_id"] == 10
    assert data["total"] == 1
    assert data["scanned"] == 1


@pytest.mark.asyncio
@respx.mock
async def test_get_project_memberships_pagination(client):
    respx.get("https://mock-op.com/api/v3/projects", params={"pageSize": "200"}).mock(
        return_value=Response(
            200,
            json={
                "_embedded": {
                    "elements": [
                        {"id": 5, "name": "Demo", "identifier": "demo"},
                    ]
                }
            },
        )
    )

    def memberships_responder(request):
        offset = int(request.url.params.get("offset", 0))
        if offset == 0:
            return Response(
                200,
                json={
                    "_embedded": {
                        "elements": [
                            {
                                "id": 11,
                                "_embedded": {
                                    "user": {"id": 8, "name": "Bob"},
                                    "roles": [{"id": 3, "name": "Tester"}],
                                },
                            }
                        ]
                    }
                },
            )
        return Response(
            200,
            json={
                "_embedded": {
                    "elements": [
                        {
                            "id": 12,
                            "_embedded": {
                                "user": {"id": 9, "name": "Cara"},
                                "roles": [{"id": 4, "name": "PM"}],
                            },
                        }
                    ]
                }
            },
        )

    respx.get("https://mock-op.com/api/v3/memberships").mock(
        side_effect=memberships_responder
    )

    async with client:
        data = await get_project_memberships(client, "demo", page_size=1, max_pages=2)

    assert {i["principal_name"] for i in data["items"]} == {"Bob", "Cara"}
    assert data["pages_scanned"] == 2
    assert data["scanned"] == 2


@pytest.mark.asyncio
@respx.mock
async def test_get_project_memberships_links_fallback(client):
    respx.get("https://mock-op.com/api/v3/projects", params={"pageSize": "200"}).mock(
        return_value=Response(
            200,
            json={
                "_embedded": {
                    "elements": [
                        {"id": 5, "name": "Demo", "identifier": "demo"},
                    ]
                }
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
                                "self": {"href": "/api/v3/memberships/20"},
                                "principal": {
                                    "href": "/api/v3/users/15",
                                    "title": "Dana",
                                },
                                "roles": [
                                    {"href": "/api/v3/roles/1", "title": "Viewer"},
                                ],
                            }
                        }
                    ]
                }
            },
        )
    )

    async with client:
        data = await get_project_memberships(client, "demo")

    assert data["items"][0]["principal_id"] == 15
    assert data["items"][0]["principal_name"] == "Dana"
    assert data["items"][0]["roles"] == ["Viewer"]
    assert data["items"][0]["membership_id"] == 20


@pytest.mark.asyncio
@respx.mock
async def test_get_project_memberships_permission_error(client):
    respx.get("https://mock-op.com/api/v3/projects", params={"pageSize": "200"}).mock(
        return_value=Response(
            200,
            json={
                "_embedded": {
                    "elements": [
                        {"id": 5, "name": "Demo", "identifier": "demo"},
                    ]
                }
            },
        )
    )

    respx.get("https://mock-op.com/api/v3/memberships").mock(
        return_value=Response(403, json={"message": "forbidden"})
    )

    async with client:
        with pytest.raises(OpenProjectHTTPError):
            await get_project_memberships(client, "demo")


@pytest.mark.asyncio
@respx.mock
async def test_get_project_memberships_group_principal(client):
    respx.get("https://mock-op.com/api/v3/projects", params={"pageSize": "200"}).mock(
        return_value=Response(
            200,
            json={
                "_embedded": {
                    "elements": [
                        {"id": 5, "name": "Demo", "identifier": "demo"},
                    ]
                }
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
                                "self": {"href": "/api/v3/memberships/30"},
                                "principal": {
                                    "href": "/api/v3/groups/99",
                                    "title": "QA Team",
                                },
                                "roles": [
                                    {"href": "/api/v3/roles/1", "title": "Viewer"},
                                ],
                            }
                        }
                    ]
                }
            },
        )
    )

    async with client:
        data = await get_project_memberships(client, "demo")

    assert data["items"][0]["principal_type"] == "Group"
    assert data["items"][0]["principal_id"] == 99
    assert data["items"][0]["principal_name"] == "QA Team"
