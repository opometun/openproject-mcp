import importlib.metadata as md

import httpx
import pytest
from openproject_mcp.transports.http import HttpConfig, build_http_app

MCP_MIN_VERSION = "1.11.0"
MCP_EXCLUDED = {"1.12.0", "1.12.1"}


def test_mcp_version_guard():
    version = md.version("mcp")
    assert version >= MCP_MIN_VERSION
    assert version not in MCP_EXCLUDED


@pytest.mark.asyncio
async def test_http_initialize_and_tools_list(monkeypatch):
    # Seed dummy env so client creation succeeds without real OpenProject calls
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "dummy")

    cfg = HttpConfig(
        host="127.0.0.1",
        port=8000,
        path="/mcp",
        json_response=True,
        stateless_http=True,
    )
    app = build_http_app(cfg)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"accept": "application/json, text/event-stream"},
        ) as client:
            # Initialize
            init_payload = {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "0.0.0"},
                },
            }
            resp = await client.post(cfg.path, json=init_payload)
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("application/json")
            body = resp.json()
            assert "result" in body
            assert "capabilities" in body["result"]

            # tools/list
            list_payload = {
                "jsonrpc": "2.0",
                "id": "2",
                "method": "tools/list",
                "params": {"cursor": None},
            }
            resp = await client.post(cfg.path, json=list_payload)
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("application/json")
            body = resp.json()
            assert "result" in body
            tools = body["result"].get("tools", [])
            assert isinstance(tools, list)
            assert len(tools) >= 1


@pytest.mark.asyncio
async def test_http_notification_returns_202(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "dummy")

    cfg = HttpConfig(json_response=True, stateless_http=True)
    app = build_http_app(cfg)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"accept": "application/json, text/event-stream"},
        ) as client:
            notification_payload = {
                "jsonrpc": "2.0",
                "method": "notifications/tools/list_changed",
                "params": {},
            }
            resp = await client.post(cfg.path, json=notification_payload)
            assert resp.status_code == 202
            # Should still be JSON content type even with empty body
            assert resp.headers["content-type"].startswith("application/json")


@pytest.mark.asyncio
async def test_http_get_without_sse_returns_406(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "dummy")

    cfg = HttpConfig(json_response=True, stateless_http=True)
    app = build_http_app(cfg)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.get(cfg.path)
            assert resp.status_code in (
                405,
                406,
            )  # streamable_http currently returns 406 without Accept: text/event-stream
