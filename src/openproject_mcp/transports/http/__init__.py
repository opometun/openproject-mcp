"""HTTP transport – requires the ``[http]`` extra (starlette + uvicorn)."""

from __future__ import annotations


def __getattr__(name: str):  # PEP 562 lazy module attribute access
    if name == "HttpConfig":
        from .config import HttpConfig

        return HttpConfig
    if name in {"build_http_app", "build_fastmcp"}:
        from .app import build_fastmcp, build_http_app

        return build_http_app if name == "build_http_app" else build_fastmcp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["HttpConfig", "build_http_app", "build_fastmcp"]
