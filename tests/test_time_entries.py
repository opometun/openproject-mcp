import json
from datetime import date

import pytest
import respx
from httpx import Response
from openproject_mcp.client import OpenProjectClient, OpenProjectHTTPError
from openproject_mcp.tools.metadata import NotFoundResolutionError
from openproject_mcp.tools.time_entries import (
    get_my_logged_time,
    list_time_entries,
    log_time,
)
from openproject_mcp.utils.time_parser import DurationParseError, parse_duration_string

# --- Parser tests ---


def test_parse_duration_basic_cases():
    assert parse_duration_string("2h") == "PT2H"
    assert parse_duration_string("30m") == "PT30M"
    assert parse_duration_string("2h 30m") == "PT2H30M"
    assert parse_duration_string("2h30m") == "PT2H30M"
    assert parse_duration_string("1.5h") == "PT1H30M"


def test_parse_duration_rounding_and_invalid():
    assert parse_duration_string("1.25h") == "PT1H15M"
    with pytest.raises(DurationParseError):
        parse_duration_string("invalid")
    with pytest.raises(DurationParseError):
        parse_duration_string("-1h")


# --- Tool tests ---


@pytest.fixture
def client():
    return OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")


@pytest.mark.asyncio
@respx.mock
async def test_log_time_posts_correct_payload(client):
    route = respx.post("https://mock-op.com/api/v3/time_entries").mock(
        return_value=Response(201, json={"_type": "TimeEntry"})
    )

    fixed_date = date(2024, 1, 2)

    async with client:
        msg = await log_time(
            client,
            work_package_id=123,
            duration="2h",
            comment="Fixing bug",
            activity_id=9,
            spent_on=fixed_date,
        )

    req = route.calls[0].request
    body = json.loads(req.content)

    assert req.url.path == "/api/v3/time_entries"
    assert body["hours"] == "PT2H"
    assert body["comment"]["raw"] == "Fixing bug"
    assert body["spentOn"] == "2024-01-02"
    assert body["_links"]["entity"]["href"] == "/api/v3/work_packages/123"
    assert body["_links"]["activity"]["href"] == "/api/v3/time_entries/activities/9"
    assert "Logged 2h to work package 123" in msg


@pytest.mark.asyncio
@respx.mock
async def test_log_time_invalid_duration_returns_error_message(client):
    async with client:
        msg = await log_time(
            client,
            work_package_id=123,
            duration="nope",
        )

    assert "Error:" in msg
    assert "2h" in msg and "30m" in msg


@pytest.mark.asyncio
@respx.mock
async def test_log_time_404_propagates(client):
    respx.post("https://mock-op.com/api/v3/time_entries").mock(
        return_value=Response(404, json={"message": "Not found"})
    )

    async with client:
        with pytest.raises(OpenProjectHTTPError):
            await log_time(client, work_package_id=123, duration="2h")


# --- list_time_entries tests ---


@pytest.mark.asyncio
@respx.mock
async def test_list_time_entries_defaults_to_me(client):
    respx.get("https://mock-op.com/api/v3/users/me").mock(
        return_value=Response(200, json={"id": 7, "name": "Me"})
    )
    route = respx.get("https://mock-op.com/api/v3/time_entries").mock(
        return_value=Response(
            200,
            json={
                "total": 1,
                "_embedded": {
                    "elements": [
                        {
                            "id": 1,
                            "hours": "PT1H30M",
                            "spentOn": "2024-01-02",
                            "comment": {"raw": "hi"},
                            "_links": {
                                "user": {"href": "/api/v3/users/7", "title": "Me"},
                                "project": {
                                    "href": "/api/v3/projects/5",
                                    "title": "Demo",
                                },
                                "workPackage": {
                                    "href": "/api/v3/work_packages/9",
                                    "title": "WP",
                                },
                            },
                        }
                    ]
                },
            },
        )
    )

    async with client:
        data = await list_time_entries(client)

    # filter sent
    params = route.calls[0].request.url.params
    filters = json.loads(params["filters"])
    assert filters[0]["user"]["values"] == ["7"]

    item = data["items"][0]
    assert item["hours_iso"] == "PT1H30M"
    assert item["minutes"] == 90
    assert item["hours_decimal"] == 1.5
    assert item["user"]["id"] == 7
    assert data["total"] == 1


@pytest.mark.asyncio
@respx.mock
async def test_list_time_entries_with_filters(client):
    respx.get("https://mock-op.com/api/v3/users/me").mock(
        return_value=Response(200, json={"id": 7, "name": "Me"})
    )
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
    route = respx.get("https://mock-op.com/api/v3/time_entries").mock(
        return_value=Response(
            200,
            json={"total": 0, "_embedded": {"elements": []}},
        )
    )

    async with client:
        await list_time_entries(
            client,
            project="demo",
            work_package=9,
            spent_from=date(2024, 1, 1),
            spent_to="2024-01-31",
        )

    filters = json.loads(route.calls[0].request.url.params["filters"])
    assert {"project": {"operator": "=", "values": ["5"]}} in filters
    assert {"workPackage": {"operator": "=", "values": ["9"]}} in filters
    assert {"spentOn": {"operator": ">=", "values": ["2024-01-01"]}} in filters
    assert {"spentOn": {"operator": "<=", "values": ["2024-01-31"]}} in filters


@pytest.mark.asyncio
@respx.mock
async def test_list_time_entries_user_by_name_via_memberships(client):
    # project resolution
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
    # memberships for project
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
                },
                "total": 1,
                "pageSize": 200,
            },
        )
    )
    route = respx.get("https://mock-op.com/api/v3/time_entries").mock(
        return_value=Response(
            200,
            json={"total": 0, "_embedded": {"elements": []}},
        )
    )

    async with client:
        await list_time_entries(client, user="Bob", project="demo")

    filters = json.loads(route.calls[0].request.url.params["filters"])
    assert {"user": {"operator": "=", "values": ["9"]}} in filters


@pytest.mark.asyncio
@respx.mock
async def test_list_time_entries_user_by_name_memberships_forbidden(client):
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
    respx.get("https://mock-op.com/api/v3/memberships").mock(
        return_value=Response(403, json={"message": "forbidden"})
    )
    respx.get("https://mock-op.com/api/v3/users").mock(
        return_value=Response(403, json={"message": "forbidden"})
    )

    async with client:
        with pytest.raises(NotFoundResolutionError):
            await list_time_entries(client, user="Bob", project="demo")


@pytest.mark.asyncio
@respx.mock
async def test_list_time_entries_user_by_name_ambiguous_memberships(client):
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
                        },
                        {
                            "_links": {
                                "principal": {
                                    "href": "/api/v3/users/10",
                                    "title": "Bob",
                                }
                            }
                        },
                    ]
                },
                "total": 2,
                "pageSize": 200,
            },
        )
    )

    async with client:
        with pytest.raises(ValueError):
            await list_time_entries(client, user="Bob", project="demo")


@pytest.mark.asyncio
@respx.mock
async def test_get_my_logged_time_wrapper(client):
    respx.get("https://mock-op.com/api/v3/users/me").mock(
        return_value=Response(200, json={"id": 7, "name": "Me"})
    )
    respx.get("https://mock-op.com/api/v3/time_entries").mock(
        return_value=Response(200, json={"_embedded": {"elements": []}, "total": 0})
    )

    async with client:
        data = await get_my_logged_time(client)

    assert data["items"] == []
