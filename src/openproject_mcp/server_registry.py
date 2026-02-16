"""Compatibility shim: re-export registry helpers from openproject_mcp.core.registry."""

from openproject_mcp.core.registry import (
    discover_tool_modules,
    iter_tool_functions,
    register_discovered_tools,
)

__all__ = [
    "discover_tool_modules",
    "iter_tool_functions",
    "register_discovered_tools",
]
