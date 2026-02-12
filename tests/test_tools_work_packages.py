import json

import openproject_mcp.tools.metadata as metadata
import pytest
import respx
from httpx import Response
from openproject_mcp.client import OpenProjectClient, OpenProjectHTTPError
from openproject_mcp.models import (
    WorkPackageCreateInput,
    WorkPackageUpdateInput,
    WorkPackageUpdateStatusInput,
)
from openproject_mcp.tools.work_packages import (
    add_comment,
    append_work_package_description,
    create_work_package,
    get_work_package,
    get_work_package_statuses,
    get_work_package_types,
    list_work_package_versions,
    list_work_packages,
    search_content,
    update_status,
    update_work_package,
)

WP_SINGLE = {
    "_type": "WorkPackage",
    "id": 42,
    "subject": "Sample",
    "lockVersion": 3,
    "description": {"raw": "Hello"},
    "_links": {
        "self": {"href": "/api/v3/work_packages/42"},
        "project": {"href": "/api/v3/projects/5", "title": "Demo"},
        "type": {"href": "/api/v3/types/1", "title": "Bug"},
        "status": {"href": "/api/v3/statuses/7", "title": "In Progress"},
        "priority": {"href": "/api/v3/priorities/3", "title": "High"},
    },
}


PROJECTS = {
    "_type": "Collection",
    "_embedded": {
        "elements": [
            {"id": 5, "name": "Demo", "identifier": "demo"},
        ]
    },
}

TYPES = {
    "_type": "Collection",
    "_embedded": {"elements": [{"id": 1, "name": "Bug"}]},
}

PRIORITIES = {
    "_type": "Collection",
    "_embedded": {"elements": [{"id": 3, "name": "High"}]},
}

STATUSES = {
    "_type": "Collection",
    "_embedded": {
        "elements": [
            {"id": 7, "name": "In Progress", "isClosed": False},
            {"id": 8, "name": "Closed", "isClosed": True},
        ]
    },
}

AVAILABLE_ASSIGNEES = {
    "_type": "Collection",
    "total": 1,
    "count": 1,
    "pageSize": 1,
    "offset": 1,
    "_embedded": {
        "elements": [
            {
                "id": 11,
                "name": "Alice Smith",
                "_links": {
                    "self": {"href": "/api/v3/users/11", "title": "Alice Smith"}
                },
            }
        ]
    },
}

PROJECT_VERSIONS = {
    "_type": "Collection",
    "total": 2,
    "count": 2,
    "pageSize": 2,
    "offset": 1,
    "_embedded": {
        "elements": [
            {"id": 21, "name": "v1.0"},
            {"id": 22, "name": "v2.0"},
        ]
    },
}


@pytest.fixture
def client():
    return OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")


@pytest.fixture(autouse=True)
def clear_cache():
    metadata._CACHE.clear()
    yield
    metadata._CACHE.clear()


@pytest.mark.asyncio
@respx.mock
async def test_get_work_package_returns_summary(client):
    respx.get("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=WP_SINGLE)
    )

    async with client:
        summary = await get_work_package(client, 42)

    assert summary["id"] == 42
    assert summary["project"]["name"] == "Demo"
    assert summary["status"]["name"] == "In Progress"
    assert summary["priority"]["name"] == "High"


@pytest.mark.asyncio
@respx.mock
async def test_list_work_packages_pagination_and_filter(client):
    collection = {
        "_type": "Collection",
        "total": 120,
        "_embedded": {"elements": [WP_SINGLE]},
    }

    respx.get("https://mock-op.com/api/v3/work_packages").mock(
        return_value=Response(200, json=collection)
    )
    respx.get("https://mock-op.com/api/v3/projects", params={"pageSize": "200"}).mock(
        return_value=Response(200, json=PROJECTS)
    )

    async with client:
        data = await list_work_packages(client, project="Demo", subject_contains="amp")

    assert data["items"][0]["id"] == 42
    assert data["pages_scanned"] == 1


@pytest.mark.asyncio
@respx.mock
async def test_create_work_package_resolves_ids_and_posts(client):
    respx.get("https://mock-op.com/api/v3/projects", params={"pageSize": "200"}).mock(
        return_value=Response(200, json=PROJECTS)
    )
    respx.get("https://mock-op.com/api/v3/types").mock(
        return_value=Response(200, json=TYPES)
    )
    respx.get("https://mock-op.com/api/v3/statuses").mock(
        return_value=Response(200, json=STATUSES)
    )
    respx.get("https://mock-op.com/api/v3/priorities").mock(
        return_value=Response(200, json=PRIORITIES)
    )
    respx.get("https://mock-op.com/api/v3/statuses").mock(
        return_value=Response(200, json=STATUSES)
    )
    respx.post("https://mock-op.com/api/v3/work_packages").mock(
        return_value=Response(201, json=WP_SINGLE)
    )

    async with client:
        summary = await create_work_package(
            client,
            data=WorkPackageCreateInput(
                project="Demo",
                type="Bug",
                subject="Sample",
                description="Hello",
                priority="High",
                status=None,
            ),
        )

    assert summary["id"] == 42


@pytest.mark.asyncio
@respx.mock
async def test_create_work_package_with_optional_fields(client):
    respx.get("https://mock-op.com/api/v3/projects", params={"pageSize": "200"}).mock(
        return_value=Response(200, json=PROJECTS)
    )
    respx.get("https://mock-op.com/api/v3/projects/5/versions").mock(
        return_value=Response(200, json=PROJECT_VERSIONS)
    )
    respx.get("https://mock-op.com/api/v3/types").mock(
        return_value=Response(200, json=TYPES)
    )
    respx.get("https://mock-op.com/api/v3/statuses").mock(
        return_value=Response(200, json=STATUSES)
    )
    respx.get("https://mock-op.com/api/v3/priorities").mock(
        return_value=Response(200, json=PRIORITIES)
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
                                }
                            }
                        }
                    ]
                }
            },
        )
    )
    post_route = respx.post("https://mock-op.com/api/v3/work_packages").mock(
        return_value=Response(201, json=WP_SINGLE)
    )

    async with client:
        await create_work_package(
            client,
            data=WorkPackageCreateInput(
                project="Demo",
                type="Bug",
                subject="Sample",
                description="Hello",
                priority="High",
                status="In Progress",
                assignee="Bob",
                accountable=9,
                start_date="2024-01-01",
                due_date="2024-01-02",
                percent_done=50,
                estimated_time="2h",
                version="v1.0",
            ),
        )

    body = json.loads(post_route.calls[0].request.content)
    assert body["subject"] == "Sample"
    assert body["percentageDone"] == 50
    assert body["_links"]["assignee"]["href"] == "/api/v3/users/9"
    assert body["_links"]["responsible"]["href"] == "/api/v3/users/9"
    assert body["_links"]["version"]["href"] == "/api/v3/versions/21"


@pytest.mark.asyncio
@respx.mock
async def test_update_status_uses_lock_version(client):
    respx.get("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=WP_SINGLE)
    )
    respx.get("https://mock-op.com/api/v3/statuses").mock(
        return_value=Response(200, json=STATUSES)
    )
    patch_route = respx.patch("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=WP_SINGLE)
    )

    async with client:
        summary = await update_status(
            client,
            data=WorkPackageUpdateStatusInput(id=42, status="In Progress"),
        )

    assert summary["status"]["name"] == "In Progress"
    import json

    body = json.loads(patch_route.calls[0].request.content)
    assert body["lockVersion"] == 3


@pytest.mark.asyncio
@respx.mock
async def test_get_work_package_404_propagates(client):
    respx.get("https://mock-op.com/api/v3/work_packages/999").mock(
        return_value=Response(404, json={"message": "Not found"})
    )

    async with client:
        with pytest.raises(OpenProjectHTTPError):
            await get_work_package(client, 999)


@pytest.mark.asyncio
@respx.mock
async def test_create_work_package_422_propagates(client):
    respx.get("https://mock-op.com/api/v3/projects", params={"pageSize": "200"}).mock(
        return_value=Response(200, json=PROJECTS)
    )
    respx.get("https://mock-op.com/api/v3/types").mock(
        return_value=Response(200, json=TYPES)
    )
    respx.post("https://mock-op.com/api/v3/work_packages").mock(
        return_value=Response(422, json={"message": "Invalid"})
    )

    async with client:
        with pytest.raises(OpenProjectHTTPError):
            await create_work_package(
                client,
                data=WorkPackageCreateInput(
                    project="Demo",
                    type="Bug",
                    subject="Bad",
                ),
            )


@pytest.mark.asyncio
@respx.mock
async def test_list_work_packages_401_propagates(client):
    respx.get("https://mock-op.com/api/v3/work_packages").mock(
        return_value=Response(401, json={"message": "Unauthorized"})
    )

    async with client:
        with pytest.raises(OpenProjectHTTPError):
            await list_work_packages(client)


@pytest.mark.asyncio
@respx.mock
async def test_add_comment_posts_comment(client):
    respx.post("https://mock-op.com/api/v3/work_packages/42/activities").mock(
        return_value=Response(
            201,
            json={
                "_links": {"self": {"href": "/api/v3/activities/9"}},
            },
        )
    )

    async with client:
        result = await add_comment(client, 42, "Hello world")

    assert result["work_package_id"] == 42
    assert result["comment"] == "Hello world"
    assert result["activity_id"] == 9
    assert result["url"].endswith("/api/v3/activities/9")


@pytest.mark.asyncio
@respx.mock
async def test_append_description_appends_and_preserves_lock_version(client):
    respx.get("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(
            200,
            json={
                **WP_SINGLE,
                "description": {"raw": "Hello"},
                "lockVersion": 3,
            },
        )
    )
    patch_route = respx.patch("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(
            200,
            json={
                **WP_SINGLE,
                "description": {"raw": "Hello\n\nMore"},
                "lockVersion": 4,
            },
        )
    )

    async with client:
        summary = await append_work_package_description(client, 42, "More")

    body = json.loads(patch_route.calls[0].request.content)
    assert body["lockVersion"] == 3
    assert body["description"]["raw"] == "Hello\n\nMore"
    assert summary["description"] == "Hello\n\nMore"


@pytest.mark.asyncio
@respx.mock
async def test_append_description_conflict_raises(client):
    respx.get("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=WP_SINGLE)
    )
    respx.patch("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(409, json={"message": "Conflict"})
    )

    async with client:
        with pytest.raises(OpenProjectHTTPError) as exc:
            await append_work_package_description(client, 42, "More")

    assert exc.value.status_code == 409


@pytest.mark.asyncio
@respx.mock
async def test_search_content_server_filter(client):
    route = respx.get("https://mock-op.com/api/v3/work_packages").mock(
        return_value=Response(
            200,
            json={
                "_embedded": {"elements": [WP_SINGLE]},
                "total": 1,
            },
        )
    )

    async with client:
        result = await search_content(client, "Sample")

    assert result["scope"] == "server_filtered"
    assert result["items"][0]["id"] == 42
    # Ensure filters param was sent
    assert "filters" in route.calls[0].request.url.params


@pytest.mark.asyncio
@respx.mock
async def test_search_content_client_fallback(client):
    # First call (with filters) returns 400 to trigger fallback; second call
    # (without filters) succeeds
    respx.get("https://mock-op.com/api/v3/work_packages").mock(
        side_effect=lambda request: Response(400, json={"message": "Bad filter"})
        if "filters" in request.url.params
        else Response(
            200,
            json={
                "_embedded": {"elements": [WP_SINGLE]},
                "total": 1,
            },
        )
    )

    async with client:
        result = await search_content(client, "Sample")

    assert result["scope"] == "client_filtered_paginated"
    assert result["items"][0]["id"] == 42


@pytest.mark.asyncio
@respx.mock
async def test_get_work_package_statuses_and_types(client):
    respx.get("https://mock-op.com/api/v3/statuses").mock(
        return_value=Response(200, json=STATUSES)
    )
    respx.get("https://mock-op.com/api/v3/types").mock(
        return_value=Response(200, json=TYPES)
    )

    async with client:
        statuses = await get_work_package_statuses(client)
        types = await get_work_package_types(client)

    assert statuses[0]["name"] == "In Progress"
    assert types[0]["name"] == "Bug"


@pytest.mark.asyncio
@respx.mock
async def test_update_work_package_multi_field(client):
    respx.get("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=WP_SINGLE)
    )
    respx.get("https://mock-op.com/api/v3/statuses").mock(
        return_value=Response(200, json=STATUSES)
    )
    respx.get("https://mock-op.com/api/v3/priorities").mock(
        return_value=Response(200, json=PRIORITIES)
    )

    patch_route = respx.patch("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(
            200,
            json={
                **WP_SINGLE,
                "subject": "Renamed",
                "_links": {
                    **WP_SINGLE["_links"],
                    "assignee": {"href": "/api/v3/users/9", "title": "Bob"},
                },
            },
        )
    )

    async with client:
        summary = await update_work_package(
            client,
            WorkPackageUpdateInput(
                id=42,
                subject="Renamed",
                status="In Progress",
                priority="High",
                assignee=9,
                percent_done=50,
            ),
        )

    body = json.loads(patch_route.calls[0].request.content)
    assert body["lockVersion"] == 3
    assert body["subject"] == "Renamed"
    assert body["percentageDone"] == 50
    assert body["_links"]["assignee"]["href"] == "/api/v3/users/9"
    assert summary["subject"] == "Renamed"


@pytest.mark.asyncio
@respx.mock
async def test_update_work_package_append_description(client):
    respx.get("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(
            200,
            json={**WP_SINGLE, "description": {"raw": "Hello"}, "lockVersion": 3},
        )
    )
    patch_route = respx.patch("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(
            200,
            json={
                **WP_SINGLE,
                "description": {"raw": "Hello\n\nMore"},
                "lockVersion": 4,
            },
        )
    )

    async with client:
        await update_work_package(
            client, WorkPackageUpdateInput(id=42, append_description="More")
        )

    body = json.loads(patch_route.calls[0].request.content)
    assert body["description"]["raw"] == "Hello\n\nMore"


@pytest.mark.asyncio
@respx.mock
async def test_update_work_package_clear_assignee(client):
    respx.get("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=WP_SINGLE)
    )
    patch_route = respx.patch("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=WP_SINGLE)
    )

    async with client:
        await update_work_package(client, WorkPackageUpdateInput(id=42, assignee=None))

    body = json.loads(patch_route.calls[0].request.content)
    assert body["_links"]["assignee"]["href"] is None


@pytest.mark.asyncio
@respx.mock
async def test_update_work_package_conflict_message(client):
    respx.get("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=WP_SINGLE)
    )
    respx.patch("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(409, json={"message": "Conflict"})
    )

    async with client:
        with pytest.raises(OpenProjectHTTPError) as excinfo:
            await update_work_package(
                client, WorkPackageUpdateInput(id=42, subject="X")
            )

    assert "lockVersion" in str(excinfo.value)


@pytest.mark.asyncio
@respx.mock
async def test_update_work_package_422_message(client):
    respx.get("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=WP_SINGLE)
    )
    respx.get("https://mock-op.com/api/v3/statuses").mock(
        return_value=Response(200, json=STATUSES)
    )
    respx.patch("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(
            422,
            json={
                "_embedded": {"errors": [{"message": "Status not allowed"}]},
                "message": "Validation failed",
            },
        )
    )

    async with client:
        with pytest.raises(OpenProjectHTTPError) as excinfo:
            await update_work_package(
                client, WorkPackageUpdateInput(id=42, status="Closed")
            )

    assert "Status not allowed" in str(excinfo.value)


@pytest.mark.asyncio
@respx.mock
async def test_update_work_package_set_accountable_by_id(client):
    respx.get("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=WP_SINGLE)
    )
    patch_route = respx.patch("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=WP_SINGLE)
    )

    async with client:
        await update_work_package(client, WorkPackageUpdateInput(id=42, accountable=11))

    body = json.loads(patch_route.calls[0].request.content)
    assert body["_links"]["responsible"]["href"] == "/api/v3/users/11"


@pytest.mark.asyncio
@respx.mock
async def test_update_work_package_assignee_by_name_uses_available_assignees(client):
    wp_with_available = {
        **WP_SINGLE,
        "_links": {
            **WP_SINGLE["_links"],
            "availableAssignees": {
                "href": "https://mock-op.com/api/v3/work_packages/42/available_assignees"
            },
            "version": {"href": None},
        },
    }

    respx.get("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=wp_with_available)
    )
    respx.get("https://mock-op.com/api/v3/work_packages/42/available_assignees").mock(
        return_value=Response(200, json=AVAILABLE_ASSIGNEES)
    )
    patch_route = respx.patch("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=WP_SINGLE)
    )

    async with client:
        await update_work_package(
            client, WorkPackageUpdateInput(id=42, assignee="Alice Smith")
        )

    body = json.loads(patch_route.calls[0].request.content)
    assert body["_links"]["assignee"]["href"] == "/api/v3/users/11"


@pytest.mark.asyncio
@respx.mock
async def test_update_work_package_set_version_by_name(client):
    wp_with_version = {
        **WP_SINGLE,
        "_links": {**WP_SINGLE["_links"], "version": {"href": "/api/v3/versions/21"}},
    }
    respx.get("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=wp_with_version)
    )
    respx.get("https://mock-op.com/api/v3/projects/5/versions").mock(
        return_value=Response(200, json=PROJECT_VERSIONS)
    )
    patch_route = respx.patch("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=WP_SINGLE)
    )

    async with client:
        await update_work_package(client, WorkPackageUpdateInput(id=42, version="v2.0"))

    body = json.loads(patch_route.calls[0].request.content)
    assert body["_links"]["version"]["href"] == "/api/v3/versions/22"


@pytest.mark.asyncio
@respx.mock
async def test_update_work_package_clear_version(client):
    wp_with_version = {
        **WP_SINGLE,
        "_links": {**WP_SINGLE["_links"], "version": {"href": "/api/v3/versions/21"}},
    }
    respx.get("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=wp_with_version)
    )
    patch_route = respx.patch("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=WP_SINGLE)
    )

    async with client:
        await update_work_package(client, WorkPackageUpdateInput(id=42, version=None))

    body = json.loads(patch_route.calls[0].request.content)
    assert body["_links"]["version"]["href"] is None


@pytest.mark.asyncio
@respx.mock
async def test_update_work_package_omit_version_not_included(client):
    respx.get("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=WP_SINGLE)
    )
    patch_route = respx.patch("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=WP_SINGLE)
    )

    async with client:
        await update_work_package(
            client, WorkPackageUpdateInput(id=42, subject="No version change")
        )

    body = json.loads(patch_route.calls[0].request.content)
    assert "_links" not in body or "version" not in body.get("_links", {})


@pytest.mark.asyncio
@respx.mock
async def test_list_work_package_versions_happy_path(client):
    wp_with_version_link = {
        **WP_SINGLE,
        "_links": {**WP_SINGLE["_links"], "version": {"href": "/api/v3/versions/21"}},
    }
    respx.get("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=wp_with_version_link)
    )
    respx.get("https://mock-op.com/api/v3/projects/5/versions").mock(
        return_value=Response(200, json=PROJECT_VERSIONS)
    )

    async with client:
        result = await list_work_package_versions(client, 42)

    assert result["items"][1]["name"] == "v2.0"
    assert result["total"] == 2


@pytest.mark.asyncio
@respx.mock
async def test_update_work_package_clear_accountable(client):
    respx.get("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=WP_SINGLE)
    )
    patch_route = respx.patch("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=WP_SINGLE)
    )

    async with client:
        await update_work_package(
            client, WorkPackageUpdateInput(id=42, accountable=None)
        )

    body = json.loads(patch_route.calls[0].request.content)
    assert body["_links"]["responsible"]["href"] is None


@pytest.mark.asyncio
@respx.mock
async def test_update_work_package_no_accountable_field_omitted(client):
    respx.get("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=WP_SINGLE)
    )
    patch_route = respx.patch("https://mock-op.com/api/v3/work_packages/42").mock(
        return_value=Response(200, json=WP_SINGLE)
    )

    async with client:
        await update_work_package(
            client, WorkPackageUpdateInput(id=42, subject="Only subject")
        )

    body = json.loads(patch_route.calls[0].request.content)
    assert "responsible" not in body.get("_links", {})
