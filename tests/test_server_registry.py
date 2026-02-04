import inspect
from types import ModuleType

import pytest
from mcp.server.fastmcp import FastMCP
from openproject_mcp.client import OpenProjectClient
from openproject_mcp.server_registry import (
    discover_tool_modules,
    register_discovered_tools,
)


def _make_module(name: str, code: str) -> ModuleType:
    module = ModuleType(name)
    exec(code, module.__dict__)
    return module


@pytest.mark.asyncio
async def test_register_discovered_tools_registers_valid_tools_only():
    code = """
async def tool_fn(client, *, foo:int=1):
    return (client.base_url, foo)

async def _private(client):
    return None

async def wrong_first(arg1, client):
    return None

def sync_func(client):
    return None
"""
    mod = _make_module("fake_mod", code)

    app = FastMCP("test")
    registered = []

    # monkeypatch tool to record registrations
    def record_tool(name):
        def decorator(fn):
            registered.append((name, fn))
            return fn

        return decorator

    app.tool = record_tool  # type: ignore[attr-defined]

    client = OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")

    register_discovered_tools(app, client, modules=[mod])

    assert [n for n, _ in registered] == ["tool_fn"]

    # wrapper signature should not expose client
    sig = inspect.signature(registered[0][1])
    assert "client" not in sig.parameters

    # call wrapper to ensure client injection works
    result = await registered[0][1](foo=5)
    assert result == ("https://mock-op.com", 5)


def test_register_discovered_tools_duplicate_names_raise():
    code1 = "async def tool_fn(client): return None"
    code2 = "async def tool_fn(client): return None"
    mod1 = _make_module("mod1", code1)
    mod2 = _make_module("mod2", code2)

    app = FastMCP("test")

    client = OpenProjectClient(base_url="https://mock-op.com", api_key="mock-key")

    with pytest.raises(ValueError):
        register_discovered_tools(app, client, modules=[mod1, mod2])


def test_discover_tool_modules_skips_import_failures(monkeypatch, caplog):
    import importlib
    import pkgutil

    # Ensure base package import works

    class Info:
        def __init__(self, name):
            self.name = name

    def fake_iter_modules(path, prefix):
        return [
            Info(prefix + "good"),
            Info(prefix + "bad"),
        ]

    good_mod = _make_module(
        "openproject_mcp.tools.good", "async def tool_fn(client): return None"
    )

    real_import_module = importlib.import_module

    def fake_import_module(name, *args, **kwargs):
        if name == "openproject_mcp.tools.bad":
            raise ImportError("boom")
        if name == "openproject_mcp.tools.good":
            return good_mod
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(pkgutil, "iter_modules", fake_iter_modules)
    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    with caplog.at_level("ERROR"):
        modules = discover_tool_modules()

    assert [m.__name__ for m in modules] == ["openproject_mcp.tools.good"]
    assert any("Failed importing tool module" in rec.message for rec in caplog.records)
