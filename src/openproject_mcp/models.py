"""Compatibility shim: re-export models from openproject_mcp.core.models."""

import importlib

_models = importlib.import_module("openproject_mcp.core.models")
__all__ = getattr(
    _models, "__all__", [name for name in dir(_models) if not name.startswith("_")]
)

for name in __all__:
    globals()[name] = getattr(_models, name)
