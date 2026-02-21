import json
import sys
import types
from contextlib import asynccontextmanager

import anyio
import httpx
import pytest
import respx
from openproject_mcp.core import registry
from openproject_mcp.core.context import (
    apply_request_context,
    client_from_context,
    get_context,
    reset_context,
)
from openproject_mcp.transports.http import HttpConfig, build_http_app


def _make_echo_module():
    module = types.ModuleType("openproject_mcp.core.tools._test_echo")
    import openproject_mcp.core.tools as tools_pkg

    async def echo(client):
        ctx = get_context(require_api_key=False, require_base_url=False)
        return {
            "request_id": ctx.request_id,
            "api_key": ctx.api_key,
            "base_url": ctx.base_url,
        }

    echo.__module__ = module.__name__
    module.echo = echo
    sys.modules[module.__name__] = module
    tools_pkg._test_echo = module
    return module


@asynccontextmanager
async def lifespan_client(app, headers=None):
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers=headers or {"accept": "application/json, text/event-stream"},
        ) as client:
            yield client


def _patch_discovery(monkeypatch, module):
    monkeypatch.setattr(
        registry,
        "discover_tool_modules",
        lambda package_name="openproject_mcp.core.tools": [module],
    )


@pytest.mark.asyncio
async def test_http_context_injected_into_tool(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "env-key")
    echo_mod = _make_echo_module()
    _patch_discovery(monkeypatch, echo_mod)

    app = build_http_app(HttpConfig(json_response=True, stateless_http=True))
    headers = {
        "accept": "application/json, text/event-stream",
        "X-OpenProject-Key": "header-key",
        "X-Request-Id": "rid-1",
    }
    async with lifespan_client(app, headers=headers) as client:
        init = {
            "jsonrpc": "2.0",
            "id": "init",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        }
        resp_init = await client.post("/mcp", json=init)
        assert resp_init.status_code == 200

        resp = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tools/call",
                "params": {"name": "echo", "arguments": {}},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        text_payload = body["result"]["content"][0]["text"]
        result = json.loads(text_payload)
        assert result["api_key"] == "header-key"
        assert result["request_id"] == "rid-1"
        assert result["base_url"] == "http://example.com"


@pytest.mark.asyncio
async def test_http_context_isolation_sequential(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "env-key")
    echo_mod = _make_echo_module()
    _patch_discovery(monkeypatch, echo_mod)

    app = build_http_app(HttpConfig(json_response=True, stateless_http=True))
    headers_base = {"accept": "application/json, text/event-stream"}
    async with lifespan_client(app) as client:
        init = {
            "jsonrpc": "2.0",
            "id": "init",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        }
        resp_init = await client.post(
            "/mcp",
            json=init,
            headers={**headers_base, "X-OpenProject-Key": "k1", "X-Request-Id": "init"},
        )
        assert resp_init.status_code == 200

        r1 = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tools/call",
                "params": {"name": "echo", "arguments": {}},
            },
            headers={**headers_base, "X-OpenProject-Key": "k1", "X-Request-Id": "r1"},
        )
        r2 = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "tools/call",
                "params": {"name": "echo", "arguments": {}},
            },
            headers={**headers_base, "X-OpenProject-Key": "k2", "X-Request-Id": "r2"},
        )
        res1 = json.loads(r1.json()["result"]["content"][0]["text"])
        res2 = json.loads(r2.json()["result"]["content"][0]["text"])
        assert res1["api_key"] == "k1"
        assert res2["api_key"] == "k2"
        assert res1["request_id"] == "r1"
        assert res2["request_id"] == "r2"


@pytest.mark.asyncio
async def test_http_context_isolation_concurrent(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "env-key")
    echo_mod = _make_echo_module()
    _patch_discovery(monkeypatch, echo_mod)

    app = build_http_app(HttpConfig(json_response=True, stateless_http=True))
    headers_base = {"accept": "application/json, text/event-stream"}

    async with lifespan_client(app) as client:
        init = {
            "jsonrpc": "2.0",
            "id": "init",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        }
        resp_init = await client.post(
            "/mcp",
            json=init,
            headers={**headers_base, "X-OpenProject-Key": "k1", "X-Request-Id": "init"},
        )
        assert resp_init.status_code == 200

        async def call(rid, key):
            resp = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": rid,
                    "method": "tools/call",
                    "params": {"name": "echo", "arguments": {}},
                },
                headers={**headers_base, "X-OpenProject-Key": key, "X-Request-Id": rid},
            )
            return json.loads(resp.json()["result"]["content"][0]["text"])

        res: dict[str, dict] = {}

        async def run_call(label, rid, key):
            res[label] = await call(rid, key)

        async with anyio.create_task_group() as tg:
            tg.start_soon(run_call, "r1", "r1", "k1")
            tg.start_soon(run_call, "r2", "r2", "k2")

        res1, res2 = res["r1"], res["r2"]
        assert res1["request_id"] == "r1"
        assert res2["request_id"] == "r2"
        assert res1["api_key"] == "k1"
        assert res2["api_key"] == "k2"


@pytest.mark.asyncio
async def test_op_client_sends_request_id_header(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "https://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "api-key")
    tokens = apply_request_context(
        api_key="api-key", base_url="https://example.com", request_id="rid-ctx"
    )
    try:
        with respx.mock(base_url="https://example.com") as router:
            route = router.get("/api/v3/foo").mock(
                return_value=httpx.Response(200, json={"ok": True})
            )
            client = client_from_context()
            await client.get("/api/v3/foo", tool="test")
            assert route.called
            sent = route.calls.last.request
            assert sent.headers.get("X-Request-Id") == "rid-ctx"
    finally:
        reset_context(tokens)


@pytest.mark.asyncio
async def test_stdio_bootstrap_seeds_context(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "api-key")
    captured = {}

    async def fake_run_stdio_async(self):
        ctx = get_context(require_api_key=True, require_base_url=True)
        captured["request_id"] = ctx.request_id
        captured["api_key"] = ctx.api_key
        captured["base_url"] = ctx.base_url
        return None

    from importlib import import_module

    from mcp.server.fastmcp import FastMCP

    stdio_mod = import_module("openproject_mcp.transports.stdio.main")
    monkeypatch.setattr(FastMCP, "run_stdio_async", fake_run_stdio_async)
    echo_mod = _make_echo_module()
    _patch_discovery(monkeypatch, echo_mod)

    await stdio_mod.main()
    assert captured["api_key"] == "api-key"
    assert captured["base_url"] == "http://example.com"
    # request_id should have been generated
    assert captured["request_id"]


@pytest.mark.asyncio
async def test_stdio_tool_uses_contextvars(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "api-key")
    echo_mod = _make_echo_module()
    _patch_discovery(monkeypatch, echo_mod)
    captured = {}

    async def fake_run_stdio_async(self):
        from openproject_mcp.core.tools import _test_echo  # type: ignore

        ctx = get_context(require_api_key=True, require_base_url=True)
        client = client_from_context()
        result = await _test_echo.echo(client)
        captured.update(result)
        captured["ctx_request_id"] = ctx.request_id
        return None

    from importlib import import_module

    from mcp.server.fastmcp import FastMCP

    stdio_mod = import_module("openproject_mcp.transports.stdio.main")
    monkeypatch.setattr(FastMCP, "run_stdio_async", fake_run_stdio_async)

    await stdio_mod.main()
    assert captured["api_key"] == "api-key"
    assert captured["base_url"] == "http://example.com"
    assert captured["request_id"] == captured["ctx_request_id"]
