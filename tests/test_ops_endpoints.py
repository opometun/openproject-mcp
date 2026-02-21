from openproject_mcp.transports.http.app import build_http_app
from openproject_mcp.transports.http.config import HttpConfig
from starlette.testclient import TestClient


def _build_app(cfg: HttpConfig | None = None):
    return build_http_app(cfg=cfg)


def test_healthz_ok_without_env(monkeypatch):
    monkeypatch.delenv("OPENPROJECT_BASE_URL", raising=False)
    monkeypatch.delenv("OPENPROJECT_API_KEY", raising=False)
    app = _build_app()
    client = TestClient(app)

    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_healthz_not_rate_limited(monkeypatch):
    monkeypatch.delenv("OPENPROJECT_BASE_URL", raising=False)
    monkeypatch.delenv("OPENPROJECT_API_KEY", raising=False)
    cfg = HttpConfig(rate_limit_rpm=1)
    app = _build_app(cfg)
    client = TestClient(app)

    for _ in range(5):
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_readyz_ok_with_defaults(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "k")
    app = _build_app()
    client = TestClient(app)

    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["failed"] == []
    assert body["checks"]["default_base_url_present"] is True
    assert body["checks"]["default_api_key_present"] is True


def test_readyz_missing_base_url(monkeypatch):
    monkeypatch.delenv("OPENPROJECT_BASE_URL", raising=False)
    monkeypatch.setenv("OPENPROJECT_API_KEY", "k")
    app = _build_app()
    client = TestClient(app)

    resp = client.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert "default_base_url_present" in body["failed"]
    assert body["checks"]["default_api_key_present"] is True


def test_readyz_header_independence(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "k")
    app = _build_app()
    client = TestClient(app)

    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_readyz_not_rate_limited(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "k")
    cfg = HttpConfig(rate_limit_rpm=1)
    app = _build_app(cfg)
    client = TestClient(app)

    for _ in range(5):
        resp = client.get("/readyz")
        assert resp.status_code == 200
        assert resp.json()["status"] in {
            "ok",
            "fail",
        }  # status depends on env, not rate limit


def test_ops_bypass_message_middleware(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://example.com")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "k")
    app = _build_app()
    client = TestClient(app)

    resp = client.get("/healthz", headers={"Accept": "text/plain"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
