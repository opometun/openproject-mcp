import json

import anyio
import httpx
import pytest
from openproject_mcp.transports.http import HttpConfig, build_http_app
from openproject_mcp.transports.http.config import (
    ERROR_PAYLOAD_TOO_LARGE,
    ERROR_TIMEOUT,
    _normalize_origin,
)
from openproject_mcp.transports.http.message_middleware import MessageHandlingMiddleware

INIT_PAYLOAD = {
    "jsonrpc": "2.0",
    "id": "1",
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "0.0.0"},
    },
}


def _client(app, headers=None):
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(
        transport=transport, base_url="http://testserver", headers=headers or {}
    )


def _base_headers(origin: str | None = None):
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "X-OpenProject-Key": "dummy",
    }
    if origin is not None:
        headers["origin"] = origin
    return headers


@pytest.fixture(autouse=True)
def seed_env(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "dummy")


@pytest.mark.asyncio
async def test_content_length_over_limit_returns_413():
    cfg = HttpConfig(
        json_response=True,
        stateless_http=True,
        max_body_bytes=10,
    )
    app = build_http_app(cfg)

    async with app.router.lifespan_context(app):
        body = json.dumps(INIT_PAYLOAD) + "EXTRA"
        headers = _base_headers()
        headers["content-length"] = str(len(body.encode()))
        async with _client(app, headers) as client:
            resp = await client.post(cfg.path, content=body)
            assert resp.status_code == 413
            payload = resp.json()
            assert payload["error"] == ERROR_PAYLOAD_TOO_LARGE
            # Security headers should still be present
            assert resp.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.asyncio
async def test_chunked_body_over_limit_returns_413_with_cors():
    origin = "http://good.com"
    cfg = HttpConfig(
        json_response=True,
        stateless_http=True,
        max_body_bytes=5,
        allowed_origins=(_normalize_origin(origin),),
    )
    app = build_http_app(cfg)

    async def gen():
        yield b"1234"
        yield b"56"

    async with app.router.lifespan_context(app):
        async with _client(app, _base_headers(origin)) as client:
            resp = await client.post(cfg.path, content=gen())
            assert resp.status_code == 413
            assert resp.json()["error"] == ERROR_PAYLOAD_TOO_LARGE
            assert resp.headers["Access-Control-Allow-Origin"] == origin
            assert "Origin" in resp.headers.get("Vary", "")


@pytest.mark.asyncio
async def test_at_limit_passes():
    body = json.dumps(INIT_PAYLOAD)
    cfg = HttpConfig(
        json_response=True,
        stateless_http=True,
        max_body_bytes=len(body.encode()),
    )
    app = build_http_app(cfg)
    async with app.router.lifespan_context(app):
        headers = _base_headers()
        headers["content-length"] = str(len(body.encode()))
        async with _client(app, headers) as client:
            resp = await client.post(cfg.path, content=body)
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_timeout_returns_configured_status(monkeypatch):
    original = MessageHandlingMiddleware.dispatch

    async def slow_dispatch(self, request, call_next):
        await anyio.sleep(0.05)
        return await original(self, request, call_next)

    monkeypatch.setattr(MessageHandlingMiddleware, "dispatch", slow_dispatch)

    cfg = HttpConfig(
        json_response=True,
        stateless_http=True,
        request_timeout_s=0.01,
        timeout_status=408,
        allowed_origins=(_normalize_origin("http://good.com"),),
    )
    app = build_http_app(cfg)

    async with app.router.lifespan_context(app):
        async with _client(app, _base_headers("http://good.com")) as client:
            resp = await client.post(cfg.path, json=INIT_PAYLOAD)
            assert resp.status_code == 408
            payload = resp.json()
            assert payload["error"] == ERROR_TIMEOUT
            assert resp.headers["Access-Control-Allow-Origin"] == "http://good.com"


def test_disable_limits_guard(monkeypatch):
    monkeypatch.setenv("MCP_MAX_BODY_BYTES", "0")
    monkeypatch.setenv("MCP_REQUEST_TIMEOUT_S", "0")
    # default allow_disable_limits is false, should raise
    with pytest.raises(ValueError):
        HttpConfig.from_env()

    monkeypatch.setenv("MCP_ALLOW_DISABLE_LIMITS", "1")
    monkeypatch.setenv("MCP_ENV", "dev")
    cfg = HttpConfig.from_env()
    assert cfg.max_body_bytes == 0
    assert cfg.request_timeout_s == 0
