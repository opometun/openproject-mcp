import json

import pytest
import respx
from httpx import Response
from openproject_mcp.client import OpenProjectClient, OpenProjectHTTPError
from openproject_mcp.tools.queries import list_queries, run_query


@pytest.fixture
def client():
    return OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")


def _queries_collection_payload():
    return {
        "_type": "Collection",
        "total": 3,
        "count": 2,
        "pageSize": 2,
        "offset": 1,
        "_embedded": {
            "elements": [
                {
                    "id": 11,
                    "name": "My View",
                    "public": True,
                    "_links": {
                        "self": {"href": "/api/v3/queries/11"},
                        "project": {"href": "/api/v3/projects/5"},
                    },
                },
                {
                    "id": 12,
                    "name": "Team View",
                    "public": False,
                    "starred": True,
                    "_links": {
                        "self": {"href": "/api/v3/queries/12"},
                        "project": {"href": "/api/v3/projects/5"},
                    },
                },
            ]
        },
    }


@pytest.mark.asyncio
@respx.mock
async def test_list_queries_with_project_filter(client):
    route = respx.get("https://mock-op.com/api/v3/queries").mock(
        return_value=Response(200, json=_queries_collection_payload())
    )

    async with client:
        data = await list_queries(client, project_id=5, offset=1, page_size=2)

    # params
    assert route.calls[0].request.url.params["offset"] == "1"
    assert route.calls[0].request.url.params["pageSize"] == "2"
    filters_param = route.calls[0].request.url.params["filters"]
    assert json.loads(filters_param) == [
        {"project_id": {"operator": "=", "values": ["5"]}}
    ]

    assert data["items"][0]["id"] == 11
    assert data["items"][0]["project_id"] == 5
    assert data["next_offset"] == 2  # 1*2 < total=3
    assert data["total"] == 3
    assert data["count"] == 2


def _query_result_payload():
    return {
        "id": 11,
        "name": "My View",
        "_embedded": {
            "results": {
                "total": 3,
                "count": 2,
                "pageSize": 2,
                "offset": 1,
                "_embedded": {
                    "elements": [
                        {
                            "id": 101,
                            "subject": "Bug one",
                            "lockVersion": 1,
                            "_links": {
                                "status": {
                                    "href": "/api/v3/statuses/1",
                                    "title": "New",
                                },
                                "priority": {
                                    "href": "/api/v3/priorities/1",
                                    "title": "Normal",
                                },
                                "project": {
                                    "href": "/api/v3/projects/5",
                                    "title": "Demo",
                                },
                                "type": {"href": "/api/v3/types/1", "title": "Bug"},
                                "self": {"href": "/api/v3/work_packages/101"},
                            },
                        },
                        {
                            "id": 102,
                            "subject": "Bug two",
                            "lockVersion": 1,
                            "_links": {
                                "status": {
                                    "href": "/api/v3/statuses/1",
                                    "title": "New",
                                },
                                "priority": {
                                    "href": "/api/v3/priorities/1",
                                    "title": "Normal",
                                },
                                "project": {
                                    "href": "/api/v3/projects/5",
                                    "title": "Demo",
                                },
                                "type": {"href": "/api/v3/types/1", "title": "Bug"},
                                "self": {"href": "/api/v3/work_packages/102"},
                            },
                        },
                    ]
                },
            }
        },
    }


@pytest.mark.asyncio
@respx.mock
async def test_run_query_happy_path(client):
    respx.get("https://mock-op.com/api/v3/queries/11").mock(
        return_value=Response(200, json=_query_result_payload())
    )

    async with client:
        data = await run_query(client, 11, offset=1, page_size=2)

    assert data["query_id"] == 11
    assert len(data["items"]) == 2
    assert data["items"][0]["id"] == 101
    assert data["offset"] == 1
    assert data["next_offset"] == 2  # 1*2 < total=3
    assert data["total"] == 3


@pytest.mark.asyncio
@respx.mock
async def test_run_query_not_found(client):
    respx.get("https://mock-op.com/api/v3/queries/99").mock(
        return_value=Response(404, json={"message": "Not found"})
    )

    async with client:
        with pytest.raises(OpenProjectHTTPError) as excinfo:
            await run_query(client, 99)

    assert excinfo.value.status_code == 404
    assert "Query not found" in str(excinfo.value)
