import pytest
from openproject_mcp.server import create_client_from_env


def test_create_client_from_env_missing_vars(monkeypatch):
    # Prevent load_dotenv from repopulating values from .env
    monkeypatch.setattr("openproject_mcp.client.load_dotenv", lambda *a, **k: None)

    monkeypatch.delenv("OPENPROJECT_BASE_URL", raising=False)
    monkeypatch.delenv("OPENPROJECT_API_KEY", raising=False)

    with pytest.raises(ValueError) as exc:
        create_client_from_env()

    assert "Missing OPENPROJECT_BASE_URL or OPENPROJECT_API_KEY" in str(exc.value)
