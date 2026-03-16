import pytest

from openproject_mcp.core.context import apply_request_context, reset_context
from openproject_mcp.core.errors import ScopeDeniedError
from openproject_mcp.core.registry import (
    REQUIRED_SCOPES_ATTR,
    _wrap_tool,
    requires_scopes,
)

# -- decorator unit tests ---------------------------------------------------- #


def test_requires_scopes_sets_attribute():
    """@requires_scopes stores scopes as a tuple on the function."""

    async def dummy(client):
        return "ok"

    decorated = requires_scopes("a", "b")(dummy)
    assert getattr(decorated, REQUIRED_SCOPES_ATTR) == ("a", "b")


def test_requires_scopes_single():
    async def dummy(client):
        return "ok"

    decorated = requires_scopes("only")(dummy)
    assert getattr(decorated, REQUIRED_SCOPES_ATTR) == ("only",)


def test_requires_scopes_preserves_function_identity():
    """Decorator should return the same function object (no extra wrapping)."""

    async def dummy(client):
        return "ok"

    decorated = requires_scopes("s")(dummy)
    assert decorated is dummy


# -- enforcement tests ------------------------------------------------------- #


def _make_tool():
    """Create a fresh tool function to avoid cross-test attribute contamination."""

    async def tool(client):
        return "ok"

    return tool


def _make_param_tool():
    """Create a fresh tool function that accepts parameters."""

    async def tool(client, value: int):
        return f"value={value}"

    return tool


@pytest.mark.asyncio
async def test_scope_denied_raises_scope_denied_error():
    """Missing scopes should raise ScopeDeniedError, not generic PermissionError."""
    func = _make_param_tool()
    secured = requires_scopes("a", "b")(func)
    wrapped = _wrap_tool(secured, lambda: None)

    tokens = list(
        apply_request_context(
            api_key="k",
            base_url="http://example.com",
            auth_scopes=("a",),
            request_id="r1",
        )
    )
    try:
        with pytest.raises(ScopeDeniedError, match="b"):
            await wrapped(value=42)
    finally:
        reset_context(tokens)


@pytest.mark.asyncio
async def test_scope_denied_is_also_permission_error():
    """ScopeDeniedError should be catchable as PermissionError."""
    func = _make_tool()
    secured = requires_scopes("x")(func)
    wrapped = _wrap_tool(secured, lambda: None)

    tokens = list(
        apply_request_context(
            api_key="k",
            base_url="http://example.com",
            auth_scopes=(),
            request_id="r2",
        )
    )
    try:
        with pytest.raises(PermissionError):
            await wrapped()
    finally:
        reset_context(tokens)


@pytest.mark.asyncio
async def test_scope_granted_passes():
    """Caller with all required scopes should succeed."""
    func = _make_tool()
    secured = requires_scopes("a", "b")(func)
    wrapped = _wrap_tool(secured, lambda: None)

    tokens = list(
        apply_request_context(
            api_key="k",
            base_url="http://example.com",
            auth_scopes=("a", "b", "c"),
            request_id="r3",
        )
    )
    try:
        result = await wrapped()
        assert result == "ok"
    finally:
        reset_context(tokens)


@pytest.mark.asyncio
async def test_no_scopes_required_always_passes():
    """A tool without @requires_scopes should work regardless of caller scopes."""
    func = _make_tool()
    wrapped = _wrap_tool(func, lambda: None)

    tokens = list(
        apply_request_context(
            api_key="k",
            base_url="http://example.com",
            auth_scopes=(),
            request_id="r4",
        )
    )
    try:
        result = await wrapped()
        assert result == "ok"
    finally:
        reset_context(tokens)


@pytest.mark.asyncio
async def test_api_key_user_rejected_by_scoped_tool():
    """API-key callers get empty scopes -> scope-gated tools must reject them."""
    func = _make_tool()
    secured = requires_scopes("wp:write")(func)
    wrapped = _wrap_tool(secured, lambda: None)

    tokens = list(
        apply_request_context(
            api_key="k",
            base_url="http://example.com",
            auth_scopes=(),
            request_id="r5",
        )
    )
    try:
        with pytest.raises(ScopeDeniedError, match="wp:write"):
            await wrapped()
    finally:
        reset_context(tokens)


@pytest.mark.asyncio
async def test_error_message_lists_missing_scopes():
    """The error message should list exactly the missing scopes, sorted."""
    func = _make_tool()
    secured = requires_scopes("z", "a", "m")(func)
    wrapped = _wrap_tool(secured, lambda: None)

    tokens = list(
        apply_request_context(
            api_key="k",
            base_url="http://example.com",
            auth_scopes=("a",),
            request_id="r6",
        )
    )
    try:
        with pytest.raises(ScopeDeniedError, match="m, z"):
            await wrapped()
    finally:
        reset_context(tokens)
