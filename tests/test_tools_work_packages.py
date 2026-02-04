import pytest
import respx
from httpx import Response
from openproject_mcp.client import OpenProjectClient
from openproject_mcp.models import WorkPackageCreateInput, WorkPackageUpdateStatusInput
from openproject_mcp.tools.work_packages import (
    create_work_package,
    get_work_package,
    list_work_packages,
    update_status,
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
    "_embedded": {"elements": [{"id": 7, "name": "In Progress", "isClosed": False}]},
}


@pytest.fixture
def client():
    return OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")


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
    assert data["next_offset"] == 50  # total implies more pages


@pytest.mark.asyncio
@respx.mock
async def test_create_work_package_resolves_ids_and_posts(client):
    respx.get("https://mock-op.com/api/v3/projects", params={"pageSize": "200"}).mock(
        return_value=Response(200, json=PROJECTS)
    )
    respx.get("https://mock-op.com/api/v3/types").mock(
        return_value=Response(200, json=TYPES)
    )
    respx.get("https://mock-op.com/api/v3/priorities").mock(
        return_value=Response(200, json=PRIORITIES)
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
