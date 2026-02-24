import httpx
import pytest
from openproject_mcp.transports.http import HttpConfig, build_http_app


def _client(app, headers=None):
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(
        transport=transport, base_url="http://testserver", headers=headers or {}
    )


_INIT = {
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
async def test_oauth_off_bearer_treated_as_api_key(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.delenv("OPENPROJECT_API_KEY", raising=False)
    cfg = HttpConfig(json_response=True, stateless_http=True, oauth_enabled=False)
    app = build_http_app(cfg)

    async with app.router.lifespan_context(app):
        async with _client(app, {"Authorization": "Bearer not.jwt"}) as client:
            resp = await client.post(
                cfg.path, json=_INIT, headers={"accept": "application/json"}
            )
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_oauth_on_invalid_jwt_401(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.delenv("OPENPROJECT_API_KEY", raising=False)
    cfg = HttpConfig(
        json_response=True,
        stateless_http=True,
        oauth_enabled=True,
        oauth_audience="dummy-client",
        oauth_jwks_url="https://www.googleapis.com/oauth2/v3/certs",
    )
    app = build_http_app(cfg)

    async with app.router.lifespan_context(app):
        async with _client(app, {"Authorization": "Bearer bad.bad.bad"}) as client:
            resp = await client.post(cfg.path, json=_INIT)
            assert resp.status_code == 401
            assert "WWW-Authenticate" in resp.headers


@pytest.mark.asyncio
async def test_oauth_on_no_auth_401_with_challenge(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.delenv("OPENPROJECT_API_KEY", raising=False)
    cfg = HttpConfig(
        json_response=True,
        stateless_http=True,
        oauth_enabled=True,
        oauth_audience="dummy-client",
    )
    app = build_http_app(cfg)

    async with app.router.lifespan_context(app):
        async with _client(app, {}) as client:
            resp = await client.post(cfg.path, json=_INIT)
            assert resp.status_code == 401
            assert "WWW-Authenticate" in resp.headers


@pytest.mark.asyncio
async def test_oauth_off_no_auth_401_without_challenge(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.delenv("OPENPROJECT_API_KEY", raising=False)
    cfg = HttpConfig(json_response=True, stateless_http=True, oauth_enabled=False)
    app = build_http_app(cfg)

    async with app.router.lifespan_context(app):
        async with _client(app, {}) as client:
            resp = await client.post(cfg.path, json=_INIT)
            assert resp.status_code == 401
            assert "WWW-Authenticate" not in resp.headers


@pytest.mark.asyncio
async def test_discovery_endpoint_present_when_enabled(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.delenv("OPENPROJECT_API_KEY", raising=False)
    cfg = HttpConfig(
        json_response=True,
        stateless_http=True,
        oauth_enabled=True,
        oauth_audience="dummy-client",
    )
    app = build_http_app(cfg)

    async with app.router.lifespan_context(app):
        async with _client(app, {}) as client:
            resp = await client.get("/.well-known/oauth-protected-resource")
            assert resp.status_code == 200
            data = resp.json()
            assert data["authorization_servers"] == list(cfg.oauth_issuer)


@pytest.mark.asyncio
async def test_discovery_endpoint_404_when_disabled(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.delenv("OPENPROJECT_API_KEY", raising=False)
    cfg = HttpConfig(json_response=True, stateless_http=True, oauth_enabled=False)
    app = build_http_app(cfg)

    async with app.router.lifespan_context(app):
        async with _client(app, {}) as client:
            resp = await client.get("/.well-known/oauth-protected-resource")
            assert resp.status_code == 404
