import uuid

import pytest
from openproject_mcp.core.context import (
    MissingApiKeyError,
    MissingBaseUrlError,
    apply_request_context,
    extract_api_key,
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


# ---------------------------------------------------------------------------
# extract_api_key unit tests
# ---------------------------------------------------------------------------


class TestExtractApiKey:
    """Verify the header cascade: X-OpenProject-Key > Bearer > X-API-Key > fallback."""

    def test_x_openproject_key_wins(self):
        headers = {
            "X-OpenProject-Key": "custom",
            "Authorization": "Bearer bearer-val",
            "X-API-Key": "xapi-val",
        }
        assert extract_api_key(headers) == "custom"

    def test_bearer_used_when_no_custom_header(self):
        headers = {"Authorization": "Bearer bearer-val", "X-API-Key": "xapi-val"}
        assert extract_api_key(headers) == "bearer-val"

    def test_x_api_key_used_when_no_bearer(self):
        headers = {"X-API-Key": "xapi-val"}
        assert extract_api_key(headers) == "xapi-val"

    def test_fallback_used_when_no_headers(self):
        assert extract_api_key({}, fallback="fb") == "fb"

    def test_none_when_no_headers_no_fallback(self):
        assert extract_api_key({}) is None

    def test_bearer_case_insensitive(self):
        headers = {"Authorization": "BEARER upper-case"}
        assert extract_api_key(headers) == "upper-case"

    def test_basic_auth_ignored(self):
        headers = {"Authorization": "Basic dXNlcjpwYXNz"}
        assert extract_api_key(headers) is None

    def test_empty_bearer_token_ignored(self):
        headers = {"Authorization": "Bearer "}
        assert extract_api_key(headers, fallback="fb") == "fb"

    def test_bearer_with_extra_whitespace(self):
        headers = {"Authorization": "Bearer   spaced-key  "}
        assert extract_api_key(headers) == "spaced-key"
