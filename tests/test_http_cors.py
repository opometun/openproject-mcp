import httpx
import pytest
from openproject_mcp.transports.http import HttpConfig, build_http_app
from openproject_mcp.transports.http.config import _normalize_origin

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
async def test_origin_not_allowlisted_returns_403():
    cfg = HttpConfig(
        json_response=True,
        stateless_http=True,
        allowed_origins=(_normalize_origin("http://good.com"),),
    )
    app = build_http_app(cfg)
    async with app.router.lifespan_context(app):
        async with _client(app, _base_headers("http://evil.com")) as client:
            resp = await client.post(cfg.path, json=INIT_PAYLOAD)
            assert resp.status_code == 403
            assert "Access-Control-Allow-Origin" not in resp.headers
            assert resp.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.asyncio
async def test_allowlisted_origin_gets_cors_headers():
    origin = "http://good.com"
    cfg = HttpConfig(
        json_response=True,
        stateless_http=True,
        allowed_origins=(_normalize_origin(origin),),
    )
    app = build_http_app(cfg)
    async with app.router.lifespan_context(app):
        async with _client(app, _base_headers(origin)) as client:
            resp = await client.post(cfg.path, json=INIT_PAYLOAD)
            assert resp.status_code == 200
            assert resp.headers["Access-Control-Allow-Origin"] == origin
            assert "Origin" in resp.headers.get("Vary", "")
            assert "X-Request-Id" in resp.headers.get(
                "Access-Control-Expose-Headers", ""
            )


@pytest.mark.asyncio
async def test_origin_null_denied():
    cfg = HttpConfig(json_response=True, stateless_http=True)
    app = build_http_app(cfg)
    async with app.router.lifespan_context(app):
        async with _client(app, _base_headers("null")) as client:
            resp = await client.post(cfg.path, json=INIT_PAYLOAD)
            assert resp.status_code == 403


@pytest.mark.asyncio
async def test_origin_with_path_denied():
    origin = "http://good.com/path"
    cfg = HttpConfig(json_response=True, stateless_http=True)
    app = build_http_app(cfg)
    async with app.router.lifespan_context(app):
        async with _client(app, _base_headers(origin)) as client:
            resp = await client.post(cfg.path, json=INIT_PAYLOAD)
            assert resp.status_code == 403


@pytest.mark.asyncio
async def test_normalization_default_port_matches():
    allow = "https://EXAMPLE.com"
    cfg = HttpConfig(
        json_response=True,
        stateless_http=True,
        allowed_origins=(_normalize_origin(allow),),
    )
    app = build_http_app(cfg)
    async with app.router.lifespan_context(app):
        async with _client(app, _base_headers("https://example.com")) as client:
            resp = await client.post(cfg.path, json=INIT_PAYLOAD)
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_non_default_port_must_match():
    allow = "http://good.com:3000"
    cfg = HttpConfig(
        json_response=True,
        stateless_http=True,
        allowed_origins=(_normalize_origin(allow),),
    )
    app = build_http_app(cfg)
    async with app.router.lifespan_context(app):
        async with _client(app, _base_headers("http://good.com:4000")) as client:
            resp = await client.post(cfg.path, json=INIT_PAYLOAD)
            assert resp.status_code == 403
        async with _client(app, _base_headers("http://good.com:3000")) as client:
            resp = await client.post(cfg.path, json=INIT_PAYLOAD)
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_dev_localhost_toggle_allows_local_when_env_dev(monkeypatch):
    monkeypatch.setenv("MCP_ENV", "dev")
    monkeypatch.setenv("MCP_DEV_ALLOW_LOCALHOST", "1")
    cfg = HttpConfig.from_env()
    app = build_http_app(cfg)
    async with app.router.lifespan_context(app):
        async with _client(app, _base_headers("http://localhost:1234")) as client:
            resp = await client.post(cfg.path, json=INIT_PAYLOAD)
            assert resp.status_code == 200


def test_dev_localhost_toggle_rejected_in_prod(monkeypatch):
    monkeypatch.setenv("MCP_ENV", "prod")
    monkeypatch.setenv("MCP_DEV_ALLOW_LOCALHOST", "1")
    with pytest.raises(ValueError):
        HttpConfig.from_env()


@pytest.mark.asyncio
async def test_preflight_allows_and_sets_vary():
    origin = "http://good.com"
    cfg = HttpConfig(
        json_response=True,
        stateless_http=True,
        allowed_origins=(_normalize_origin(origin),),
        cors_max_age=300,
    )
    app = build_http_app(cfg)
    async with app.router.lifespan_context(app):
        headers = {
            "origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, X-OpenProject-Key",
        }
        async with _client(app, headers) as client:
            resp = await client.options(cfg.path)
            assert resp.status_code == 204
            vary = resp.headers.get("Vary", "")
            assert "Origin" in vary
            assert "Access-Control-Request-Method" in vary
            assert "Access-Control-Request-Headers" in vary
            assert resp.headers.get("Access-Control-Max-Age") == "300"
            assert "X-OpenProject-Key" in resp.headers.get(
                "Access-Control-Allow-Headers", ""
            )


@pytest.mark.asyncio
async def test_no_origin_passes_without_cors_headers():
    cfg = HttpConfig(json_response=True, stateless_http=True)
    app = build_http_app(cfg)
    async with app.router.lifespan_context(app):
        async with _client(app, _base_headers(None)) as client:
            resp = await client.post(cfg.path, json=INIT_PAYLOAD)
            assert resp.status_code == 200
            assert "Access-Control-Allow-Origin" not in resp.headers


@pytest.mark.asyncio
async def test_security_headers_present_on_accept_error():
    origin = "http://good.com"
    cfg = HttpConfig(
        json_response=True,
        stateless_http=True,
        allowed_origins=(_normalize_origin(origin),),
    )
    app = build_http_app(cfg)
    async with app.router.lifespan_context(app):
        bad_accept_headers = _base_headers(origin)
        bad_accept_headers["accept"] = "text/event-stream"
        async with _client(app, bad_accept_headers) as client:
            resp = await client.post(cfg.path, json=INIT_PAYLOAD)
            assert resp.status_code == 406
            assert resp.headers["X-Content-Type-Options"] == "nosniff"
            assert resp.headers["Access-Control-Allow-Origin"] == origin


@pytest.mark.asyncio
async def test_hsts_only_when_trusted_proxy_and_https(monkeypatch):
    origin = "https://good.com"
    monkeypatch.setenv("MCP_ENV", "dev")
    monkeypatch.setenv("MCP_DEV_ALLOW_LOCALHOST", "0")
    cfg = HttpConfig(
        json_response=True,
        stateless_http=True,
        allowed_origins=(_normalize_origin(origin),),
        hsts_enabled=True,
        trust_proxy_headers=True,
        trusted_proxies=("127.0.0.1/32",),
    )
    app = build_http_app(cfg)
    async with app.router.lifespan_context(app):
        headers = _base_headers(origin)
        headers["forwarded"] = "proto=https;host=good.com"
        async with _client(app, headers) as client:
            resp = await client.post(cfg.path, json=INIT_PAYLOAD)
            assert resp.status_code == 200
            assert "Strict-Transport-Security" in resp.headers


@pytest.mark.asyncio
async def test_hsts_not_set_when_not_trusted(monkeypatch):
    origin = "https://good.com"
    cfg = HttpConfig(
        json_response=True,
        stateless_http=True,
        allowed_origins=(_normalize_origin(origin),),
        hsts_enabled=True,
        trust_proxy_headers=False,
    )
    app = build_http_app(cfg)
    async with app.router.lifespan_context(app):
        headers = _base_headers(origin)
        headers["x-forwarded-proto"] = "https"
        async with _client(app, headers) as client:
            resp = await client.post(cfg.path, json=INIT_PAYLOAD)
            assert resp.status_code == 200
            assert "Strict-Transport-Security" not in resp.headers
