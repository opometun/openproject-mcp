"""openproject_mcp package exports."""

from .client import (
    OpenProjectClient,
    OpenProjectClientError,
    OpenProjectHTTPError,
    OpenProjectModelValidationError,
    OpenProjectParseError,
    RetryConfig,
)
from .hal import (
    get_embedded,
    get_link,
    get_link_href,
    get_link_title,
    parse_id_from_href,
    resolve_property,
)
from .server import main as run_server
from .server_registry import discover_tool_modules, register_discovered_tools

__all__ = [
    # Client
    "OpenProjectClient",
    "RetryConfig",
    # Exceptions
    "OpenProjectClientError",
    "OpenProjectHTTPError",
    "OpenProjectParseError",
    "OpenProjectModelValidationError",
    # HAL utilities
    "get_link",
    "get_link_href",
    "get_link_title",
    "get_embedded",
    "parse_id_from_href",
    "resolve_property",
    # Server utilities
    "run_server",
    "discover_tool_modules",
    "register_discovered_tools",
]
