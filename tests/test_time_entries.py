import json
from datetime import date

import pytest
import respx
from httpx import Response
from openproject_mcp.client import OpenProjectClient
from openproject_mcp.tools.time_entries import log_time
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
