from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from types import ModuleType
from typing import Callable, Iterable, List, Set, get_origin, get_type_hints

from .client import OpenProjectClient

log = logging.getLogger("openproject_mcp.core.registry")


# --- Discovery helpers ----------------------------------------------------- #


def discover_tool_modules(
    package_name: str = "openproject_mcp.core.tools",
) -> List[ModuleType]:
    """Import all modules under the given tools package, skipping failures."""
    modules: List[ModuleType] = []
    base_pkg = importlib.import_module(package_name)

    for finder in pkgutil.iter_modules(base_pkg.__path__, base_pkg.__name__ + "."):
        name = finder.name
        try:
            module = importlib.import_module(name)
            modules.append(module)
        except Exception as exc:  # pragma: no cover - logged, not fatal
            log.error("Failed importing tool module %s: %s", name, exc)
            continue

    return modules


def iter_tool_functions(module: ModuleType) -> Iterable[Callable]:
    """Yield functions that satisfy the tool convention."""
    for _, func in inspect.getmembers(module, inspect.iscoroutinefunction):
        if func.__name__.startswith("_"):
            continue
        # Skip helper resolvers not meant to be exposed as tools
        if func.__name__ == "resolve_metadata_id":
            log.debug("Skipping %s.%s (helper)", module.__name__, func.__name__)
            continue
        if func.__module__ != module.__name__:
            # Skip imported functions
            continue

        sig = inspect.signature(func)
        params = list(sig.parameters.values())
        if not params or params[0].name != "client":
            log.debug(
                "Skipping %s.%s: first parameter must be 'client'",
                module.__name__,
                func.__name__,
            )
            continue

        # Skip helpers that take Type[...] or other generics that FastMCP/Pydantic
        # can't schema-generate (e.g., resolve_metadata_id).
        bad_annotation = False
        for p in params[1:]:
            origin = get_origin(p.annotation)
            if origin is type:
                bad_annotation = True
                break
        if bad_annotation:
            log.debug(
                "Skipping %s.%s: unsupported parameter annotation (Type[...] detected)",
                module.__name__,
                func.__name__,
            )
            continue

        yield func


# --- Wrapping / registration ---------------------------------------------- #


def _wrap_tool(
    func: Callable, client_provider: Callable[[], OpenProjectClient]
) -> Callable:
    """Return a wrapper that injects client and hides it from the signature."""
    original_sig = inspect.signature(func)
    type_hints = get_type_hints(func)

    new_params = []
    for i, (name, param) in enumerate(original_sig.parameters.items()):
        if i == 0 and name == "client":
            continue  # drop injected client
        ann = type_hints.get(name, param.annotation)
        new_params.append(param.replace(annotation=ann))

    return_ann = type_hints.get("return", original_sig.return_annotation)
    new_sig = inspect.Signature(parameters=new_params, return_annotation=return_ann)

    async def wrapped(*args, **kwargs):
        client = client_provider()
        return await func(client, *args, **kwargs)

    wrapped.__name__ = func.__name__
    wrapped.__doc__ = func.__doc__
    wrapped.__module__ = func.__module__
    wrapped.__signature__ = new_sig  # type: ignore[attr-defined]
    return wrapped


def register_discovered_tools(
    app,
    client_provider: Callable[[], OpenProjectClient] | OpenProjectClient,
    modules: List[ModuleType] | None = None,
) -> None:
    """Register discovered tools on an app that exposes a .tool decorator."""
    if isinstance(client_provider, OpenProjectClient):
        _client = client_provider

        def client_provider():
            return _client

    if not hasattr(app, "tool"):
        raise TypeError("app must expose a 'tool' decorator")

    modules = modules or discover_tool_modules()
    seen_names: Set[str] = set()

    for module in modules:
        for func in iter_tool_functions(module):
            name = func.__name__
            if name in seen_names:
                raise ValueError(f"Duplicate tool name detected: {name}")

            wrapped = _wrap_tool(func, client_provider)
            app.tool(name=name)(wrapped)
            seen_names.add(name)
            log.info("Registered tool: %s (%s)", name, module.__name__)
