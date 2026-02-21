import logging

import httpx
import pytest
import respx
from openproject_mcp.core.client import (
    OpenProjectClient,
    OpenProjectClientError,
    RetryConfig,
)
from openproject_mcp.transports.http.request_id_middleware import RequestIdMiddleware
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient


def _app(handler):
    return Starlette(
        routes=[Route("/mcp", handler, methods=["POST"])],
        middleware=[Middleware(RequestIdMiddleware)],
    )


def test_request_id_logged_success(caplog):
    async def handler(request):
        return JSONResponse({"ok": True})

    app = _app(handler)
    with (
        TestClient(app) as client,
        caplog.at_level(logging.INFO, logger="openproject_mcp.observability"),
    ):
        resp = client.post("/mcp", json={"hello": "world"})

    assert resp.status_code == 200
    record = next(r for r in caplog.records if r.getMessage() == "http_request")
    assert record.request_id == resp.headers["X-Request-Id"]
    assert record.status == 200
    assert record.path == "/mcp"
    assert record.duration_ms >= 0


def test_request_id_logged_on_exception(caplog):
    async def handler(request):
        raise ValueError("boom")

    app = _app(handler)
    with (
        TestClient(app, raise_server_exceptions=False) as client,
        caplog.at_level(logging.INFO, logger="openproject_mcp.observability"),
    ):
        resp = client.post("/mcp", json={})

    assert resp.status_code == 500
    record = next(r for r in caplog.records if r.getMessage() == "http_request")
    assert record.status == "exception"
    assert record.request_id
    assert record.path == "/mcp"


@pytest.mark.asyncio
@respx.mock
async def test_op_client_logs_success(caplog):
    caplog.set_level(logging.INFO, logger="openproject_mcp.observability")
    route = respx.get("https://example.com/api/v3/foo").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    client = OpenProjectClient(
        base_url="https://example.com",
        api_key="key",
        request_id="rid-success",
    )
    try:
        await client.get("/api/v3/foo", tool="foo")
    finally:
        await client.aclose()

    assert route.called
    record = next(r for r in caplog.records if r.getMessage() == "op_call")
    assert record.request_id == "rid-success"
    assert record.tool == "foo"
    assert record.status == 200
    assert record.endpoint == "/api/v3/foo"


@pytest.mark.asyncio
@respx.mock
async def test_op_client_logs_exception(caplog):
    caplog.set_level(logging.INFO, logger="openproject_mcp.observability")
    respx.get("https://example.com/api/v3/bar").mock(
        side_effect=httpx.ConnectTimeout("boom")
    )
    client = OpenProjectClient(
        base_url="https://example.com",
        api_key="key",
        request_id="rid-fail",
        retry=RetryConfig(max_retries=0),
    )
    with pytest.raises(OpenProjectClientError):
        await client.get("/api/v3/bar", tool="bar")
    await client.aclose()

    record = next(r for r in caplog.records if r.getMessage() == "op_call")
    assert record.request_id == "rid-fail"
    assert record.tool == "bar"
    assert record.status == "exception"
    assert record.error_type == "ConnectTimeout"
    assert record.endpoint == "/api/v3/bar"
