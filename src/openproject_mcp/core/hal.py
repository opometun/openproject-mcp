from typing import Any, Dict, Optional


def get_link(payload: Dict[str, Any], relation: str) -> Optional[Dict[str, Any]]:
    """
    Safely retrieves a link object from the _links dictionary.
    """
    if not payload or "_links" not in payload:
        return None
    return payload["_links"].get(relation)


def get_link_href(payload: Dict[str, Any], relation: str) -> Optional[str]:
    """
    Extracts the 'href' (URL) from a specific link relation.
    Example: get_link_href(wp_json, 'status') -> '/api/v3/statuses/1'
    """
    link = get_link(payload, relation)
    return link.get("href") if link else None


def get_link_title(payload: Dict[str, Any], relation: str) -> Optional[str]:
    """
    Extracts the 'title' (readable name) from a specific link relation.
    Example: get_link_title(wp_json, 'status') -> 'In Progress'
    """
    link = get_link(payload, relation)
    return link.get("title") if link else None


def get_embedded(payload: Dict[str, Any], relation: str) -> Optional[Dict[str, Any]]:
    """
    Extracts an embedded resource from the _embedded dictionary.
    Example: get_embedded(wp_json, 'status') -> {'id': 1, 'name': 'In Progress', ...}
    """
    if not payload or "_embedded" not in payload:
        return None
    return payload["_embedded"].get(relation)


def parse_id_from_href(href: Optional[str]) -> Optional[int]:
    """
    Extracts the ID from a RESTful URL.
    Example: '/api/v3/work_packages/42' -> 42
    """
    if not href:
        return None
    try:
        # Splits by '/' and takes the last non-empty segment
        return int(href.strip("/").split("/")[-1])
    except (ValueError, IndexError):
        return None


def resolve_property(payload: Dict[str, Any], property_name: str) -> Any:
    """
    Smart extraction: Tries to find the property in the root object first.
    If not found, looks for it in '_links' (returning the title).

    This is useful because OpenProject sometimes puts 'status' in root
    and sometimes only as a link.
    """
    # Direct property (e.g., 'subject')
    if property_name in payload:
        return payload[property_name]

    # Link title (e.g., 'status' might be a link)
    title = get_link_title(payload, property_name)
    if title:
        return title

    # Embedded resource
    return get_embedded(payload, property_name)
