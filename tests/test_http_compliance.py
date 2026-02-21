from contextlib import asynccontextmanager

import httpx
import pytest
from openproject_mcp.transports.http import HttpConfig, build_http_app
from openproject_mcp.transports.http.rate_limit import time as rl_time


def make_app(cfg: HttpConfig | None = None):
    return build_http_app(cfg or HttpConfig(json_response=True, stateless_http=True))


@asynccontextmanager
async def lifespan_client(app, headers=None):
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", headers=headers or {}
        ) as client:
            yield client


@pytest.mark.asyncio
async def test_notification_only_returns_202(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "dummy")
    app = make_app()
    async with lifespan_client(
        app, {"accept": "application/json", "X-OpenProject-Key": "dummy"}
    ) as client:
        payload = {
            "jsonrpc": "2.0",
            "method": "notifications/tools/list_changed",
            "params": {},
        }
        resp = await client.post("/mcp", json=payload)
        assert resp.status_code == 202
        assert resp.content == b""
        # content-type may be absent; if present it should be json
        ctype = resp.headers.get("content-type")
        assert ctype is None or ctype.startswith("application/json")


@pytest.mark.asyncio
async def test_json_request_returns_200(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "dummy")
    app = make_app()
    async with lifespan_client(
        app, {"accept": "application/json", "X-OpenProject-Key": "dummy"}
    ) as client:
        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        }
        resp = await client.post("/mcp", json=payload)
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("application/json")
        body = resp.json()
        assert "result" in body


@pytest.mark.asyncio
async def test_get_mcp_returns_405(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "dummy")
    app = make_app()
    async with lifespan_client(
        app, {"accept": "application/json", "X-OpenProject-Key": "dummy"}
    ) as client:
        resp = await client.get("/mcp")
        assert resp.status_code == 405


@pytest.mark.asyncio
async def test_accept_sse_only_returns_406(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "dummy")
    app = make_app()
    async with lifespan_client(
        app, {"accept": "text/event-stream", "X-OpenProject-Key": "dummy"}
    ) as client:
        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "t", "version": "0"},
            },
        }
        resp = await client.post("/mcp", json=payload)
        assert resp.status_code == 406


@pytest.mark.asyncio
async def test_missing_api_key_returns_401(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.delenv("OPENPROJECT_API_KEY", raising=False)
    app = make_app()
    async with lifespan_client(app, {"accept": "application/json"}) as client:
        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "t", "version": "0"},
            },
        }
        resp = await client.post("/mcp", json=payload)
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_payload_too_large_returns_413(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "dummy")
    cfg = HttpConfig(json_response=True, stateless_http=True, max_body_bytes=5)
    app = make_app(cfg)
    async with lifespan_client(
        app, {"accept": "application/json", "X-OpenProject-Key": "dummy"}
    ) as client:
        resp = await client.post("/mcp", content=b"123456")
        assert resp.status_code == 413


@pytest.mark.asyncio
async def test_rate_limit_returns_429(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "dummy")
    cfg = HttpConfig(json_response=True, stateless_http=True, rate_limit_rpm=1)
    app = make_app(cfg)

    # Freeze time to keep requests in the same window
    monkeypatch.setattr(rl_time, "time", lambda: 1000.0)

    async with lifespan_client(
        app, {"accept": "application/json", "X-OpenProject-Key": "dummy"}
    ) as client:
        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "t", "version": "0"},
            },
        }
        first = await client.post("/mcp", json=payload)
        assert first.status_code in {200, 202}

        second = await client.post("/mcp", json=payload)
        assert second.status_code == 429


@pytest.mark.asyncio
async def test_error_mapping_parse_error(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "dummy")
    app = make_app()
    async with lifespan_client(
        app, {"accept": "application/json", "X-OpenProject-Key": "dummy"}
    ) as client:
        resp = await client.post("/mcp", content=b"{ not-json")
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == -32700


@pytest.mark.asyncio
async def test_error_mapping_invalid_request(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "dummy")
    app = make_app()
    async with lifespan_client(
        app, {"accept": "application/json", "X-OpenProject-Key": "dummy"}
    ) as client:
        resp = await client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": "1", "result": {}}
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == -32600
