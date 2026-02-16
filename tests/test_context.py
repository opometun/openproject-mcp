import uuid

import pytest
from openproject_mcp.core.context import (
    MissingApiKeyError,
    MissingBaseUrlError,
    apply_request_context,
    get_context,
    reset_context,
    seed_from_env,
    seed_from_headers,
)


def test_seed_from_env_missing(monkeypatch):
    monkeypatch.delenv("OPENPROJECT_BASE_URL", raising=False)
    monkeypatch.delenv("OPENPROJECT_API_KEY", raising=False)
    with pytest.raises(MissingBaseUrlError):
        seed_from_env()


def test_seed_from_headers_precedence_env_fallback(monkeypatch):
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://env-base")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "env-key")
    ctx = seed_from_headers({})
    assert ctx.base_url == "http://env-base"
    assert ctx.api_key == "env-key"


def test_apply_and_get_context_isolated():
    tokens = apply_request_context(
        api_key="k1",
        base_url="b1",
        request_id="r1",
        user_agent="ua1",
    )
    ctx = get_context()
    assert ctx.api_key == "k1"
    assert ctx.base_url == "b1"
    assert ctx.request_id == "r1"
    assert ctx.user_agent == "ua1"
    reset_context(tokens)
    with pytest.raises(MissingApiKeyError):
        get_context()


def test_request_id_generated():
    tokens = apply_request_context(api_key="k", base_url="b")
    ctx = get_context()
    uuid.UUID(hex=ctx.request_id)  # should parse
    reset_context(tokens)
