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


# -- multi-issuer ----------------------------------------------------------- #


@pytest.mark.asyncio
async def test_multi_issuer_audience_mismatch_returns_401(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    cfg = HttpConfig(
        json_response=True,
        stateless_http=True,
        oauth_enabled=True,
        oauth_audience=("a1", "a2"),
        oauth_issuer=("iss1", "iss2"),
        oauth_jwks_url=("http://jwks1", "http://jwks2"),
    )
    app = build_http_app(cfg)
    async with app.router.lifespan_context(app):
        from openproject_mcp.transports.http import auth_middleware

        async def fake_validate(self, token):
            from jwt import InvalidTokenError

            raise InvalidTokenError("boom")

        monkeypatch.setattr(
            auth_middleware.AuthMiddleware, "_validate_jwt", fake_validate
        )

        async with _client(
            app,
            {"Authorization": "Bearer bad.bad.bad", "accept": "application/json"},
        ) as client:
            resp = await client.post(cfg.path, json=_INIT)
            assert resp.status_code == 401


# -- global required scopes (auth_middleware level) ------------------------- #


@pytest.mark.asyncio
async def test_required_scopes_missing_returns_401(monkeypatch):
    """When a JWT lacks globally-required scopes, _validate_jwt raises → 401."""
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    cfg = HttpConfig(
        json_response=True,
        stateless_http=True,
        oauth_enabled=True,
        oauth_audience=("dummy-client",),
        oauth_required_scopes=("openid", "email"),
        oauth_issuer=("accounts.google.com",),
        oauth_jwks_url=("https://www.googleapis.com/oauth2/v3/certs",),
    )
    app = build_http_app(cfg)
    async with app.router.lifespan_context(app):
        from jwt import InvalidTokenError

        from openproject_mcp.transports.http import auth_middleware

        async def fake_validate(self, token):
            # Simulate real path: _validate_jwt checks scopes and fails
            raise InvalidTokenError("missing required scopes")

        monkeypatch.setattr(
            auth_middleware.AuthMiddleware, "_validate_jwt", fake_validate
        )

        async with _client(
            app,
            {"Authorization": "Bearer bad.bad.bad", "accept": "application/json"},
        ) as client:
            resp = await client.post(cfg.path, json=_INIT)
            assert resp.status_code == 401


@pytest.mark.asyncio
async def test_jwt_scopes_propagated_to_context(monkeypatch):
    """Scopes from JWT claims reach request.state.oauth_scopes and ContextVars."""
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "test-key")
    cfg = HttpConfig(
        json_response=True,
        stateless_http=True,
        oauth_enabled=True,
        oauth_audience=("dummy-client",),
        oauth_issuer=("accounts.google.com",),
        oauth_jwks_url=("https://www.googleapis.com/oauth2/v3/certs",),
    )
    app = build_http_app(cfg)
    async with app.router.lifespan_context(app):
        from openproject_mcp.transports.http import auth_middleware

        async def fake_validate(self, token):
            return {
                "iss": "accounts.google.com",
                "sub": "user123",
                "scope": "wp:read wp:write wp:comment",
                "aud": "dummy-client",
            }

        monkeypatch.setattr(
            auth_middleware.AuthMiddleware, "_validate_jwt", fake_validate
        )

        async with _client(
            app,
            {"Authorization": "Bearer good.good.good", "accept": "application/json"},
        ) as client:
            resp = await client.post(cfg.path, json=_INIT)
            # Should succeed (200) since JWT is valid and no global scopes required
            assert resp.status_code == 200


# -- discovery endpoint scopes ---------------------------------------------- #


@pytest.mark.asyncio
async def test_discovery_scopes_include_tool_scopes(monkeypatch):
    """The discovery endpoint should list tool-level scopes."""
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    cfg = HttpConfig(
        json_response=True,
        stateless_http=True,
        oauth_enabled=True,
        oauth_audience=("dummy-client",),
    )
    app = build_http_app(cfg)
    async with app.router.lifespan_context(app):
        async with _client(app) as client:
            resp = await client.get("/.well-known/oauth-protected-resource")
            assert resp.status_code == 200
            data = resp.json()
            scopes = data["scopes_supported"]
            # Must include at least the tool scopes
            for scope in ("wp:write", "wp:comment", "time:write", "attachment:write"):
                assert scope in scopes, f"{scope} missing from scopes_supported"


# -- config validation ------------------------------------------------------ #


def test_config_normalizes_string_to_tuple():
    """Passing bare strings for oauth fields should auto-normalize to tuples."""
    cfg = HttpConfig(
        oauth_issuer="single-issuer",
        oauth_audience="single-audience",
        oauth_jwks_url="https://example.com/jwks",
    )
    assert cfg.oauth_issuer == ("single-issuer",)
    assert cfg.oauth_audience == ("single-audience",)
    assert cfg.oauth_jwks_url == ("https://example.com/jwks",)


def test_config_issuer_jwks_count_mismatch(monkeypatch):
    """Mismatched issuer/JWKS counts should raise ValueError."""
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OAUTH_ENABLED", "true")
    monkeypatch.setenv("OAUTH_ISSUER", "iss1,iss2")
    monkeypatch.setenv("OAUTH_JWKS_URL", "http://jwks1")
    monkeypatch.setenv("OAUTH_AUDIENCE", "aud1")
    with pytest.raises(ValueError, match="same number of entries"):
        HttpConfig.from_env()


def test_config_audience_count_mismatch(monkeypatch):
    """Audience count must be 1 or match issuers."""
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OAUTH_ENABLED", "true")
    monkeypatch.setenv("OAUTH_ISSUER", "iss1,iss2,iss3")
    monkeypatch.setenv("OAUTH_JWKS_URL", "http://j1,http://j2,http://j3")
    monkeypatch.setenv("OAUTH_AUDIENCE", "a1,a2")  # 2 != 3 and != 1
    with pytest.raises(ValueError, match="OAUTH_AUDIENCE count must be 1 or match"):
        HttpConfig.from_env()


def test_config_from_env_defaults_when_unset(monkeypatch):
    """When OAUTH_ISSUER / OAUTH_JWKS_URL are not set, class defaults should be used."""
    monkeypatch.delenv("OAUTH_ISSUER", raising=False)
    monkeypatch.delenv("OAUTH_JWKS_URL", raising=False)
    monkeypatch.delenv("OAUTH_AUDIENCE", raising=False)
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    cfg = HttpConfig.from_env()
    assert cfg.oauth_issuer == ("accounts.google.com",)
    assert cfg.oauth_jwks_url == ("https://www.googleapis.com/oauth2/v3/certs",)
    assert cfg.oauth_audience is None


def test_config_required_scopes_from_env(monkeypatch):
    """OAUTH_REQUIRED_SCOPES CSV should parse into a tuple."""
    monkeypatch.setenv("OAUTH_REQUIRED_SCOPES", "openid, email, profile")
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    cfg = HttpConfig.from_env()
    assert cfg.oauth_required_scopes == ("openid", "email", "profile")


# -- tool annotation verification ------------------------------------------- #


def test_write_tools_are_annotated():
    """All write-mutating tool functions must have @requires_scopes."""
    from openproject_mcp.core.registry import REQUIRED_SCOPES_ATTR
    from openproject_mcp.core.tools import attachments, time_entries, work_packages

    annotated = {
        (work_packages, "create_work_package", "wp:write"),
        (work_packages, "update_status", "wp:write"),
        (work_packages, "update_work_package", "wp:write"),
        (work_packages, "add_comment", "wp:comment"),
        (work_packages, "append_work_package_description", "wp:write"),
        (time_entries, "log_time", "time:write"),
        (attachments, "attach_file_to_wp", "attachment:write"),
    }
    for module, func_name, expected_scope in annotated:
        func = getattr(module, func_name)
        scopes = getattr(func, REQUIRED_SCOPES_ATTR, None)
        assert scopes is not None, f"{func_name} missing @requires_scopes"
        assert expected_scope in scopes, (
            f"{func_name}: expected scope '{expected_scope}' in {scopes}"
        )


def test_read_tools_are_not_annotated():
    """Read-only tools should NOT have @requires_scopes (open by default)."""
    from openproject_mcp.core.registry import REQUIRED_SCOPES_ATTR
    from openproject_mcp.core.tools import projects, users, work_packages

    read_funcs = [
        (work_packages, "get_work_package"),
        (work_packages, "list_work_packages"),
        (work_packages, "search_content"),
        (projects, "list_projects"),
        (projects, "get_project_summary"),
        (users, "get_user_by_id"),
        (users, "get_users"),
    ]
    for module, func_name in read_funcs:
        func = getattr(module, func_name)
        assert not hasattr(func, REQUIRED_SCOPES_ATTR), (
            f"Read tool {func_name} should not have @requires_scopes"
        )
