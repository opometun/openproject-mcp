import pytest
import respx
from httpx import Response
from openproject_mcp.client import OpenProjectClient, OpenProjectHTTPError
from openproject_mcp.tools.users import get_user_by_id, get_users


@pytest.fixture
def client():
    return OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")


@pytest.mark.asyncio
@respx.mock
async def test_get_user_by_id_merges_custom_fields_from_props_and_links(client):
    respx.get("https://mock-op.com/api/v3/users/7").mock(
        return_value=Response(
            200,
            json={
                "id": 7,
                "name": "Ada Lovelace",
                "login": "ada",
                "status": "active",
                "mail": "ada@example.com",
                "customField1": "Blue",
                "_links": {
                    "self": {"href": "/api/v3/users/7"},
                    "customField2": {
                        "title": "CF2 title",
                        "href": "/api/v3/custom_options/2",
                    },
                    "customField1": {
                        "title": "CF1 title",
                        "href": "/api/v3/custom_options/1",
                    },
                },
            },
        )
    )

    async with client:
        profile = await get_user_by_id(client, 7)

    assert profile["id"] == 7
    assert profile["name"] == "Ada Lovelace"
    assert profile["status"] == "active"
    assert profile["email"] == "ada@example.com"

    # customField1 should merge property value and link data
    cf1 = next(cf for cf in profile["custom_fields"] if cf["key"] == "customField1")
    assert cf1["id"] == 1
    assert cf1["value"] == "Blue"
    assert cf1["title"] == "CF1 title"
    assert cf1["href"] == "/api/v3/custom_options/1"
    assert {"title": "CF1 title", "href": "/api/v3/custom_options/1"} in cf1["links"]

    cf2 = next(cf for cf in profile["custom_fields"] if cf["key"] == "customField2")
    assert cf2["id"] == 2
    assert cf2["value"] == "CF2 title"
    assert cf2["href"] == "/api/v3/custom_options/2"


@pytest.mark.asyncio
@respx.mock
async def test_get_user_by_id_handles_list_links_and_missing_email(client):
    respx.get("https://mock-op.com/api/v3/users/8").mock(
        return_value=Response(
            200,
            json={
                "id": 8,
                "name": "Bob",
                "status": "locked",
                "_links": {
                    "self": {"href": "/api/v3/users/8"},
                    "customField3": [
                        {
                            "title": "List CF",
                            "href": "/api/v3/custom_options/3",
                        }
                    ],
                },
            },
        )
    )

    async with client:
        profile = await get_user_by_id(client, 8)

    assert profile["email"] is None
    assert profile["status"] == "locked"
    cf3 = profile["custom_fields"][0]
    assert cf3["key"] == "customField3"
    assert cf3["value"] == "List CF"
    assert cf3["href"] == "/api/v3/custom_options/3"
    assert {"title": "List CF", "href": "/api/v3/custom_options/3"} in cf3["links"]


@pytest.mark.asyncio
@respx.mock
async def test_get_user_by_id_permission_denied(client):
    respx.get("https://mock-op.com/api/v3/users/9").mock(
        return_value=Response(403, json={"message": "Forbidden"})
    )

    async with client:
        with pytest.raises(OpenProjectHTTPError) as excinfo:
            await get_user_by_id(client, 9)

    err = excinfo.value
    assert err.status_code == 403
    assert "Permission denied" in str(err)


@pytest.mark.asyncio
@respx.mock
async def test_get_user_by_id_not_visible_404(client):
    respx.get("https://mock-op.com/api/v3/users/10").mock(
        return_value=Response(404, json={"message": "Not found"})
    )

    async with client:
        with pytest.raises(OpenProjectHTTPError) as excinfo:
            await get_user_by_id(client, 10)

    err = excinfo.value
    assert err.status_code == 404
    assert "not found" in str(err).lower()


# --- get_users tests ---


@pytest.mark.asyncio
@respx.mock
async def test_get_users_global_listing_with_email_filter(client):
    respx.get("https://mock-op.com/api/v3/users").mock(
        return_value=Response(
            200,
            json={
                "total": 3,
                "_embedded": {
                    "elements": [
                        {"id": 1, "name": "Alice", "mail": "alice@example.com"},
                        {"id": 2, "name": "Bob", "mail": "bob@example.com"},
                    ]
                },
            },
        )
    )

    async with client:
        data = await get_users(client, email_filter="bob")

    assert data["items"] == [
        {
            "id": 2,
            "name": "Bob",
            "login": None,
            "email": "bob@example.com",
            "admin": None,
            "status": None,
        }
    ]
    assert data["warnings"] is None


@pytest.mark.asyncio
@respx.mock
async def test_get_users_falls_back_to_memberships(client):
    respx.get("https://mock-op.com/api/v3/projects", params={"pageSize": "200"}).mock(
        return_value=Response(
            200,
            json={
                "_embedded": {
                    "elements": [{"id": 5, "name": "Demo", "identifier": "demo"}]
                }
            },
        )
    )
    # global forbidden
    respx.get("https://mock-op.com/api/v3/users").mock(
        return_value=Response(403, json={"message": "forbidden"})
    )
    respx.get("https://mock-op.com/api/v3/memberships").mock(
        return_value=Response(
            200,
            json={
                "_embedded": {
                    "elements": [
                        {
                            "_links": {
                                "principal": {"href": "/api/v3/users/9", "title": "Bob"}
                            }
                        }
                    ]
                },
                "total": 1,
            },
        )
    )

    async with client:
        data = await get_users(client, project="demo")

    assert data["items"][0]["id"] == 9
    assert data["items"][0]["name"] == "Bob"


@pytest.mark.asyncio
@respx.mock
async def test_get_users_memberships_forbidden_and_global_forbidden(client):
    respx.get("https://mock-op.com/api/v3/projects", params={"pageSize": "200"}).mock(
        return_value=Response(
            200,
            json={
                "_embedded": {
                    "elements": [{"id": 5, "name": "Demo", "identifier": "demo"}]
                }
            },
        )
    )
    respx.get("https://mock-op.com/api/v3/users").mock(
        return_value=Response(403, json={"message": "forbidden"})
    )
    respx.get("https://mock-op.com/api/v3/memberships").mock(
        return_value=Response(403, json={"message": "forbidden"})
    )

    async with client:
        with pytest.raises(OpenProjectHTTPError):
            await get_users(client, project="demo")


@pytest.mark.asyncio
@respx.mock
async def test_get_users_email_filter_warning_when_hidden(client):
    respx.get("https://mock-op.com/api/v3/users").mock(
        return_value=Response(
            200,
            json={
                "total": 1,
                "_embedded": {"elements": [{"id": 1, "name": "Alice"}]},
            },
        )
    )

    async with client:
        data = await get_users(client, email_filter="alice")

    assert data["items"] == []
    assert data["warnings"] is not None
