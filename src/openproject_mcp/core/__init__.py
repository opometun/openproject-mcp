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

# from .errors import (
#     OpenProjectClientError as _OpenProjectClientError,
# )
# from .errors import (
#     OpenProjectHTTPError as _OpenProjectHTTPError,
# )
# from .errors import (
#     OpenProjectModelValidationError as _OpenProjectModelValidationError,
# )
# from .errors import (
#     OpenProjectParseError as _OpenProjectParseError,
# )
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
]
