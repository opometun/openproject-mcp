from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from openproject_mcp.client import OpenProjectClient
from openproject_mcp.models import ProjectRef
from openproject_mcp.tools._collections import embedded_elements
from openproject_mcp.tools.memberships import get_project_memberships
from openproject_mcp.tools.metadata import _resolve_project_id_for_types

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

    elements = embedded_elements(payload)
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
        "items": [
            {"id": p.id, "name": p.name, "identifier": p.identifier} for p in projects
        ],
        "offset": offset,
        "page_size": page_size,
        "total": total,
        "next_offset": next_offset,
    }


async def get_project_summary(
    client: OpenProjectClient, project_id: int | str
) -> Dict[str, Any]:
    """
    Provide a concise summary of a project: basic info, work package total,
    versions, and member role counts.
    """
    project_resolved = await _resolve_project_id_for_types(client, project_id)
    project = await client.get(f"/api/v3/projects/{project_resolved}", tool="projects")

    def _description_text(desc: Any) -> str:
        if isinstance(desc, dict):
            return str(desc.get("raw") or "")
        return ""

    # Work package total (fallback-friendly)
    wp_total = None
    try:
        wp_payload = await client.get(
            "/api/v3/work_packages",
            params={
                "pageSize": 1,
                "filters": json.dumps(
                    [{"project": {"operator": "=", "values": [str(project_resolved)]}}]
                ),
            },
            tool="projects",
        )
        wp_total = wp_payload.get("total") if isinstance(wp_payload, dict) else None
    except Exception:
        wp_total = None

    # Versions (paged)
    versions: List[Dict[str, Any]] = []
    offset = 0
    page_size = MAX_PAGE_SIZE
    while True:
        resp = await client.get(
            f"/api/v3/projects/{project_resolved}/versions",
            params={"offset": offset, "pageSize": page_size},
            tool="projects",
        )
        batch = embedded_elements(resp)
        versions.extend(
            [
                {"id": v.get("id"), "name": v.get("name")}
                for v in batch
                if isinstance(v, dict)
            ]
        )
        if len(batch) < page_size:
            break
        offset += page_size

    # Members via existing helper
    members = await get_project_memberships(
        client, project_resolved, page_size=200, max_pages=5
    )
    role_counts: Dict[str, int] = {}
    for m in members.get("items", []):
        for r in m.get("roles", []):
            role_counts[r] = role_counts.get(r, 0) + 1

    return {
        "project": {
            "id": project.get("id"),
            "name": project.get("name"),
            "identifier": project.get("identifier"),
            "active": project.get("active"),
            "description_text": _description_text(project.get("description")),
        },
        "work_packages": {"total": wp_total},
        "versions": {"total": len(versions), "items": versions},
        "members": {"total": members.get("scanned"), "roles": role_counts},
    }
