"""Compatibility shim: re-export HAL helpers from openproject_mcp.core.hal."""

from openproject_mcp.core.hal import (
    get_embedded,
    get_link,
    get_link_href,
    get_link_title,
    parse_id_from_href,
    resolve_property,
)

__all__ = [
    "get_link",
    "get_link_href",
    "get_link_title",
    "get_embedded",
    "parse_id_from_href",
    "resolve_property",
]
