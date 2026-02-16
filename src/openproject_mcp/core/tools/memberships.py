from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from openproject_mcp.core.client import OpenProjectClient, OpenProjectHTTPError
from openproject_mcp.core.hal import parse_id_from_href
from openproject_mcp.core.tools._collections import embedded_elements
from openproject_mcp.core.tools.metadata import _norm, _resolve_project_id_for_types

MAX_PAGE_SIZE = 200


def _clamp_page_size(page_size: int) -> int:
    return max(1, min(page_size, MAX_PAGE_SIZE))


def _principal_from_membership(item: Dict[str, Any]) -> Dict[str, Optional[Any]]:
    principal_link = (
        item.get("_links", {}).get("principal", {}) if isinstance(item, dict) else {}
    )
    href = principal_link.get("href")
    name = principal_link.get("title")
    principal_id = None
    principal_type = None

    if href:
        principal_id = parse_id_from_href(href)
        # crude type inference from path segments
        if "/users/" in href:
            principal_type = "User"
        elif "/groups/" in href:
            principal_type = "Group"

    # Fallback to embedded user when principal link is absent or title missing
    if (href is None or name is None) and isinstance(item, dict):
        user_emb = item.get("_embedded", {}).get("user", {})
        if isinstance(user_emb, dict):
            if principal_id is None:
                principal_id = user_emb.get("id")
            if name is None:
                name = user_emb.get("name")
            if href is None and user_emb.get("_links", {}):
                href = user_emb.get("_links", {}).get("self", {}).get("href")
            if principal_type is None:
                principal_type = "User" if user_emb else None

    return {
        "id": principal_id,
        "name": name,
        "href": href,
        "type": principal_type,
    }


def _roles_from_membership(item: Dict[str, Any]) -> List[str]:
    roles_emb = item.get("_embedded", {}).get("roles", [])
    names: List[str] = []
    if isinstance(roles_emb, list):
        names.extend(
            [r.get("name") for r in roles_emb if isinstance(r, dict) and r.get("name")]
        )
    roles_links = item.get("_links", {}).get("roles", [])
    if isinstance(roles_links, list):
        for r in roles_links:
            title = r.get("title") if isinstance(r, dict) else None
            if title:
                names.append(title)
    return names


async def get_project_memberships(
    client: OpenProjectClient,
    project: int | str,
    *,
    page_size: int = 100,
    max_pages: int = 5,
    sort: bool = False,
) -> Dict[str, Any]:
    """
    List project memberships (users and their roles) for a project.
    - project: id or identifier/name (case-insensitive).
    - pagination: page_size clamped to 1..200, up to max_pages pages.
    Returns: {items, total?, scanned, pages_scanned}
    Each item: {membership_id, user_id, user_name, user_href, roles}
    """
    project_id = await _resolve_project_id_for_types(client, project)

    page_size = _clamp_page_size(page_size)
    items: List[Dict[str, Any]] = []
    offset = 0
    pages_scanned = 0
    filters = [{"project": {"operator": "=", "values": [str(project_id)]}}]

    for _ in range(max_pages):
        try:
            payload = await client.get(
                "/api/v3/memberships",
                params={
                    "offset": offset,
                    "pageSize": page_size,
                    "filters": json.dumps(filters),
                },
                tool="memberships",
            )
        except OpenProjectHTTPError as exc:
            if exc.status_code == 403:
                raise OpenProjectHTTPError(
                    status_code=403,
                    method="GET",
                    url=f"{client.base_url}/api/v3/memberships",
                    message="Permission denied: unable to view project memberships.",
                ) from exc
            raise

        batch = embedded_elements(payload)
        for m in batch:
            membership_id = m.get("id") if isinstance(m, dict) else None
            if membership_id is None:
                membership_id = parse_id_from_href(
                    m.get("_links", {}).get("self", {}).get("href", "")
                    if isinstance(m, dict)
                    else ""
                )

            principal = _principal_from_membership(m if isinstance(m, dict) else {})
            roles = _roles_from_membership(m if isinstance(m, dict) else {})

            items.append(
                {
                    "membership_id": membership_id,
                    "principal_id": principal["id"],
                    "principal_name": principal["name"],
                    "principal_href": principal["href"],
                    "principal_type": principal["type"],
                    "roles": roles,
                }
            )

        pages_scanned += 1
        offset += page_size
        if len(batch) < page_size:
            break

    if sort:
        items.sort(
            key=lambda i: (_norm(i.get("user_name") or ""), i.get("user_id") or 0)
        )

    total = payload.get("total") if isinstance(payload, dict) else None
    return {
        "items": items,
        "total": total if isinstance(total, int) else None,
        "scanned": len(items),
        "pages_scanned": pages_scanned,
    }
