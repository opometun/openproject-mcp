import httpx
import pytest
from openproject_mcp.transports.http import HttpConfig, build_http_app


def _client(app, headers=None):
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(
        transport=transport, base_url="http://testserver", headers=headers or {}
    )


@pytest.mark.asyncio
async def test_missing_api_key_returns_401(monkeypatch):
    monkeypatch.delenv("OPENPROJECT_BASE_URL", raising=False)
    monkeypatch.delenv("OPENPROJECT_API_KEY", raising=False)

    cfg = HttpConfig(json_response=True, stateless_http=True)
    app = build_http_app(cfg)

    async with app.router.lifespan_context(app):
        async with _client(app, {"accept": "application/json"}) as client:
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
            resp = await client.post(cfg.path, json=payload)
            assert resp.status_code == 401
            body = resp.json()
            assert body["error"] == "missing_api_key"
            assert resp.headers["content-type"].startswith("application/json")


@pytest.mark.asyncio
async def test_present_api_key_allows_request(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "env-key")

    cfg = HttpConfig(json_response=True, stateless_http=True)
    app = build_http_app(cfg)

    async with app.router.lifespan_context(app):
        async with _client(
            app, {"accept": "application/json", "X-OpenProject-Key": "header-key"}
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
            resp = await client.post(cfg.path, json=payload)
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("application/json")


@pytest.mark.asyncio
async def test_context_isolation_between_requests(monkeypatch):
    monkeypatch.delenv("OPENPROJECT_BASE_URL", raising=False)
    monkeypatch.delenv("OPENPROJECT_API_KEY", raising=False)
    cfg = HttpConfig(json_response=True, stateless_http=True)
    app = build_http_app(cfg)

    async with app.router.lifespan_context(app):
        # first request with key1 succeeds
        async with _client(
            app, {"X-OpenProject-Key": "key1", "accept": "application/json"}
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
            resp = await client.post(cfg.path, json=payload)
            assert resp.status_code == 500  # base_url missing, but key used
        # second request without key should not reuse prior key; should 401
        async with _client(app, {"accept": "application/json"}) as client:
            resp = await client.post(cfg.path, json=payload)
            assert resp.status_code == 401


@pytest.mark.asyncio
async def test_base_url_header_ignored(monkeypatch):
    monkeypatch.delenv("OPENPROJECT_BASE_URL", raising=False)
    monkeypatch.setenv("OPENPROJECT_API_KEY", "env-key")
    cfg = HttpConfig(json_response=True, stateless_http=True)
    app = build_http_app(cfg)

    async with app.router.lifespan_context(app):
        async with _client(
            app,
            {
                "X-OpenProject-Key": "env-key",
                "X-OpenProject-BaseUrl": "http://bad-override",
                "accept": "application/json",
            },
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
            resp = await client.post(cfg.path, json=payload)
            # Because base_url header is ignored and env base_url missing, expect 500
            assert resp.status_code == 500
            body = resp.json()
            assert body["error"] == "missing_base_url"


@pytest.mark.asyncio
async def test_api_key_not_logged(monkeypatch, caplog):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "env-key")
    caplog.set_level("INFO")

    cfg = HttpConfig(json_response=True, stateless_http=True)
    app = build_http_app(cfg)

    api_key = "super-secret-key"
    async with app.router.lifespan_context(app):
        async with _client(
            app,
            {"X-OpenProject-Key": api_key, "accept": "application/json"},
        ) as client:
            await client.post(
                cfg.path,
                json={
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "t", "version": "0"},
                    },
                },
            )
    assert api_key not in " ".join(rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_missing_base_url_returns_500(monkeypatch):
    monkeypatch.delenv("OPENPROJECT_BASE_URL", raising=False)
    monkeypatch.setenv("OPENPROJECT_API_KEY", "env-key")

    cfg = HttpConfig(json_response=True, stateless_http=True)
    app = build_http_app(cfg)

    async with app.router.lifespan_context(app):
        async with _client(app, {"X-OpenProject-Key": "header-key"}) as client:
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
            resp = await client.post(cfg.path, json=payload)
            assert resp.status_code == 500
            body = resp.json()
            assert body["error"] == "missing_base_url"
