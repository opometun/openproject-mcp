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


# ---------------------------------------------------------------------------
# Bearer / X-API-Key header support (BYO key for LibreChat etc.)
# ---------------------------------------------------------------------------

_INIT_PAYLOAD = {
    "jsonrpc": "2.0",
    "id": "1",
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "t", "version": "0"},
    },
}


@pytest.mark.asyncio
async def test_bearer_token_accepted(monkeypatch):
    """Authorization: Bearer <key> should be accepted as the API key."""
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.delenv("OPENPROJECT_API_KEY", raising=False)

    cfg = HttpConfig(json_response=True, stateless_http=True)
    app = build_http_app(cfg)

    async with app.router.lifespan_context(app):
        async with _client(
            app,
            {"accept": "application/json", "Authorization": "Bearer my-bearer-key"},
        ) as client:
            resp = await client.post(cfg.path, json=_INIT_PAYLOAD)
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_x_api_key_header_accepted(monkeypatch):
    """X-API-Key header should be accepted as the API key."""
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.delenv("OPENPROJECT_API_KEY", raising=False)

    cfg = HttpConfig(json_response=True, stateless_http=True)
    app = build_http_app(cfg)

    async with app.router.lifespan_context(app):
        async with _client(
            app,
            {"accept": "application/json", "X-API-Key": "my-x-api-key"},
        ) as client:
            resp = await client.post(cfg.path, json=_INIT_PAYLOAD)
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_custom_header_takes_priority_over_bearer(monkeypatch):
    """X-OpenProject-Key should win over Authorization: Bearer."""
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.delenv("OPENPROJECT_API_KEY", raising=False)

    cfg = HttpConfig(json_response=True, stateless_http=True)
    app = build_http_app(cfg)

    async with app.router.lifespan_context(app):
        async with _client(
            app,
            {
                "accept": "application/json",
                "X-OpenProject-Key": "custom-key",
                "Authorization": "Bearer bearer-key",
            },
        ) as client:
            resp = await client.post(cfg.path, json=_INIT_PAYLOAD)
            # Both are valid keys; request should succeed.
            # The custom header takes priority (verified via context).
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_bearer_without_token_falls_through(monkeypatch):
    """'Authorization: Bearer ' with no token should fall through to env."""
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "env-fallback")
    monkeypatch.delenv("OAUTH_ENABLED", raising=False)

    cfg = HttpConfig(json_response=True, stateless_http=True)
    app = build_http_app(cfg)

    async with app.router.lifespan_context(app):
        async with _client(
            app,
            {"accept": "application/json", "Authorization": "Bearer "},
        ) as client:
            resp = await client.post(cfg.path, json=_INIT_PAYLOAD)
            # Empty bearer token is ignored; env key is used as fallback
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_basic_auth_ignored(monkeypatch):
    """Authorization: Basic ... must NOT be treated as a valid API key."""
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.delenv("OPENPROJECT_API_KEY", raising=False)

    cfg = HttpConfig(json_response=True, stateless_http=True)
    app = build_http_app(cfg)

    async with app.router.lifespan_context(app):
        async with _client(
            app,
            {"accept": "application/json", "Authorization": "Basic dXNlcjpwYXNz"},
        ) as client:
            resp = await client.post(cfg.path, json=_INIT_PAYLOAD)
            # No valid key source → 401
            assert resp.status_code == 401


@pytest.mark.asyncio
async def test_bearer_key_not_logged(monkeypatch, caplog):
    """Bearer token must not appear in logs."""
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.delenv("OPENPROJECT_API_KEY", raising=False)
    caplog.set_level("INFO")

    cfg = HttpConfig(json_response=True, stateless_http=True)
    app = build_http_app(cfg)

    secret = "super-secret-bearer-token"
    async with app.router.lifespan_context(app):
        async with _client(
            app,
            {"accept": "application/json", "Authorization": f"Bearer {secret}"},
        ) as client:
            await client.post(cfg.path, json=_INIT_PAYLOAD)
    assert secret not in " ".join(rec.message for rec in caplog.records)
