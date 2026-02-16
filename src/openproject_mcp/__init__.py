"""Top-level exports (compat) delegating to openproject_mcp.core."""

from openproject_mcp.core import (
    OpenProjectClient,
    OpenProjectClientError,
    OpenProjectHTTPError,
    OpenProjectModelValidationError,
    OpenProjectParseError,
    RetryConfig,
    create_client_from_env,
    discover_tool_modules,
    get_embedded,
    get_link,
    get_link_href,
    get_link_title,
    iter_tool_functions,
    parse_id_from_href,
    register_discovered_tools,
    resolve_property,
)

__all__ = [
    "OpenProjectClient",
    "RetryConfig",
    "OpenProjectClientError",
    "OpenProjectHTTPError",
    "OpenProjectParseError",
    "OpenProjectModelValidationError",
    "get_link",
    "get_link_href",
    "get_link_title",
    "get_embedded",
    "parse_id_from_href",
    "resolve_property",
    "create_client_from_env",
    "discover_tool_modules",
    "iter_tool_functions",
    "register_discovered_tools",
]
