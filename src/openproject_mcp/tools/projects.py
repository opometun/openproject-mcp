from __future__ import annotations

from typing import Any, Dict, List, Optional

from openproject_mcp.client import OpenProjectClient
from openproject_mcp.models import ProjectRef
from openproject_mcp.tools.metadata import _embedded_elements

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def _clamp_page_size(page_size: int) -> int:
    """Clamp page_size into a safe range to avoid huge payloads."""
    return max(1, min(page_size, MAX_PAGE_SIZE))


async def list_projects(
    client: OpenProjectClient,
    *,
    offset: int = 0,
    page_size: int = DEFAULT_PAGE_SIZE,
    name_contains: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List projects with offset/page_size pagination.

    Returns:
        {
            "items": [{"id": int, "name": str}, ...],
            "offset": int,
            "page_size": int,
            "total": int | None,
            "next_offset": int | None,
        }
    """
    if offset < 0:
        raise ValueError("offset must be >= 0")

    page_size = _clamp_page_size(page_size)

    params = {"offset": offset, "pageSize": page_size}
    payload = await client.get("/api/v3/projects", params=params, tool="projects")

    elements = _embedded_elements(payload)
    projects: List[ProjectRef] = [ProjectRef.model_validate(e) for e in elements]

    if name_contains:
        needle = name_contains.strip().casefold()
        projects = [p for p in projects if needle in p.name.casefold()]

    total: Optional[int] = (
        payload.get("total") if isinstance(payload.get("total"), int) else None
    )
    if total is None:
        total = len(projects)

    next_offset: Optional[int] = None
    if isinstance(total, int) and (offset + page_size) < total:
        next_offset = offset + page_size

    return {
        "items": [{"id": p.id, "name": p.name} for p in projects],
        "offset": offset,
        "page_size": page_size,
        "total": total,
        "next_offset": next_offset,
    }
