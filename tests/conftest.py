import pytest


def _has_http_extra() -> bool:
    """Return True when starlette + uvicorn are importable."""
    try:
        import starlette  # noqa: F401
        import uvicorn  # noqa: F401

        return True
    except ImportError:
        return False


_HTTP_AVAILABLE = _has_http_extra()


def pytest_collection_modifyitems(config, items):
    """Skip HTTP-transport tests when [http] extra is not installed."""
    if _HTTP_AVAILABLE:
        return  # all tests can run
    skip_http = pytest.mark.skip(
        reason="HTTP extra not installed: pip install 'openproject-mcp[http]'"
    )
    for item in items:
        # Only skip tests in test_http_* files, not tests that merely mention "http"
        parts = item.nodeid.split("::")
        filename = parts[0].rsplit("/", 1)[-1] if parts else ""
        if filename.startswith("test_http"):
            item.add_marker(skip_http)
