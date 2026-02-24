"""Integration tests for /link/openproject and /unlink/openproject HTTP endpoints.

Exercises the full Starlette middleware stack (Auth → Context bypass → handler)
through the ASGI test client.
"""

from __future__ import annotations

import httpx
import pytest
from openproject_mcp.transports.http.app import build_http_app
from openproject_mcp.transports.http.config import HttpConfig


def _app(monkeypatch) -> object:
    """Build a test-ready ASGI app with dummy env vars."""
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "dummy")
    cfg = HttpConfig(json_response=True, stateless_http=True)
    return build_http_app(cfg)


def _client(app, headers=None):
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers=headers or {},
    )


# ------------------------------------------------------------------
# Link
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_link_requires_auth(monkeypatch):
    """POST /link/openproject without any auth → 401."""
    app = _app(monkeypatch)
    async with app.router.lifespan_context(app):
        async with _client(app) as client:
            resp = await client.post(
                "/link/openproject",
                json={"api_token": "tok"},
            )
            assert resp.status_code == 401
            assert resp.json()["error"] == "unauthorized"


@pytest.mark.asyncio
async def test_link_requires_api_token_field(monkeypatch):
    """POST /link/openproject with auth but without api_token → 400."""
    app = _app(monkeypatch)
    async with app.router.lifespan_context(app):
        async with _client(app, {"X-OpenProject-Key": "my-key"}) as client:
            resp = await client.post(
                "/link/openproject",
                json={"base_url": "http://op.example.com"},
            )
            assert resp.status_code == 400
            body = resp.json()
            assert body["error"] == "invalid_request"
            assert "api_token" in body["message"]


@pytest.mark.asyncio
async def test_link_success(monkeypatch):
    """POST /link/openproject with valid payload → 200 and token stored."""
    app = _app(monkeypatch)
    async with app.router.lifespan_context(app):
        async with _client(app, {"X-OpenProject-Key": "my-key"}) as client:
            resp = await client.post(
                "/link/openproject",
                json={"api_token": "tok123", "base_url": "http://op.example.com"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_link_via_bearer(monkeypatch):
    """POST /link/openproject using Bearer token (non-JWT, OAuth disabled) → 200."""
    app = _app(monkeypatch)
    async with app.router.lifespan_context(app):
        async with _client(app, {"Authorization": "Bearer my-api-key"}) as client:
            resp = await client.post(
                "/link/openproject",
                json={"api_token": "tok-bearer"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"


# ------------------------------------------------------------------
# Unlink
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unlink_requires_auth(monkeypatch):
    """POST /unlink/openproject without auth → 401."""
    app = _app(monkeypatch)
    async with app.router.lifespan_context(app):
        async with _client(app) as client:
            resp = await client.post("/unlink/openproject")
            assert resp.status_code == 401
            assert resp.json()["error"] == "unauthorized"


@pytest.mark.asyncio
async def test_unlink_success(monkeypatch):
    """POST /unlink/openproject with auth → 200 even if nothing was linked."""
    app = _app(monkeypatch)
    async with app.router.lifespan_context(app):
        async with _client(app, {"X-OpenProject-Key": "my-key"}) as client:
            resp = await client.post("/unlink/openproject")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"


# ------------------------------------------------------------------
# Round-trip: link → verify stored → unlink → verify gone
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_link_then_unlink_round_trip(monkeypatch):
    """Link a token, verify it's in the store, unlink, verify it's gone."""
    app = _app(monkeypatch)
    async with app.router.lifespan_context(app):
        headers = {"X-OpenProject-Key": "round-trip-key"}
        async with _client(app, headers) as client:
            # Link
            resp = await client.post(
                "/link/openproject",
                json={"api_token": "secret-op-token", "base_url": "http://op.test"},
            )
            assert resp.status_code == 200

            # Verify store has the token (access via app state)
            from openproject_mcp.transports.http.token_store import (
                principal_from_api_key,
            )

            principal = principal_from_api_key("round-trip-key")
            record = app.state.token_store.get(principal)
            assert record is not None
            assert record.api_token == "secret-op-token"
            assert record.base_url == "http://op.test"
            assert record.status == "active"

            # Unlink
            resp = await client.post("/unlink/openproject")
            assert resp.status_code == 200

            # Verify store is empty for this principal
            assert app.state.token_store.get(principal) is None
