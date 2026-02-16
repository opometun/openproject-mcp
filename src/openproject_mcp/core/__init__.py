"""Core domain surface for openproject-mcp (transport-agnostic)."""

from .client import (
    OpenProjectClient,
    OpenProjectClientError,
    OpenProjectHTTPError,
    OpenProjectModelValidationError,
    OpenProjectParseError,
    RetryConfig,
)
from .config import create_client_from_env, load_env_config
from .context import (
    MissingApiKeyError,
    MissingBaseUrlError,
    RequestContext,
    apply_request_context,
    ensure_request_id,
    get_context,
    reset_context,
    seed_from_env,
    seed_from_headers,
)
from .hal import (
    get_embedded,
    get_link,
    get_link_href,
    get_link_title,
    parse_id_from_href,
    resolve_property,
)
from .registry import (
    discover_tool_modules,
    iter_tool_functions,
    register_discovered_tools,
)

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
    # Config helpers
    "create_client_from_env",
    "load_env_config",
    # Registry helpers
    "discover_tool_modules",
    "iter_tool_functions",
    "register_discovered_tools",
    # Context
    "RequestContext",
    "MissingApiKeyError",
    "MissingBaseUrlError",
    "seed_from_env",
    "seed_from_headers",
    "get_context",
    "apply_request_context",
    "reset_context",
    "ensure_request_id",
]
