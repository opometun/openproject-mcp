"""
Shared helpers for working with OpenProject HAL collections.
"""

from typing import Any, Dict, List


def embedded_elements(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract elements list from a HAL collection payload.
    Raises ValueError if the expected structure is missing or malformed.
    """
    embedded = payload.get("_embedded", {})
    elements = embedded.get("elements", [])
    if not isinstance(elements, list):
        raise ValueError("Expected _embedded.elements to be a list.")
    return [e for e in elements if isinstance(e, dict)]
