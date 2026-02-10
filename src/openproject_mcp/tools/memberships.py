from __future__ import annotations

from typing import Any, Dict, List, Optional

from openproject_mcp.client import OpenProjectClient, OpenProjectHTTPError
from openproject_mcp.hal import parse_id_from_href
from openproject_mcp.tools._collections import embedded_elements
from openproject_mcp.tools.metadata import _norm, _resolve_project_id_for_types

MAX_PAGE_SIZE = 200


def _clamp_page_size(page_size: int) -> int:
    return max(1, min(page_size, MAX_PAGE_SIZE))


def _user_from_membership(item: Dict[str, Any]) -> Dict[str, Optional[Any]]:
    user_emb = (
        item.get("_embedded", {}).get("user", {}) if isinstance(item, dict) else {}
    )
    user_links = (
        item.get("_links", {}).get("user", {}) if isinstance(item, dict) else {}
    )

    user_id = user_emb.get("id")
    user_name = user_emb.get("name")
    user_href = None

    href = user_links.get("href")
    if href:
        user_href = href
        if user_id is None:
            user_id = parse_id_from_href(href)
    if user_name is None and isinstance(user_links, dict):
        user_name = user_links.get("title")

    return {
        "id": user_id,
        "name": user_name,
        "href": user_href,
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

    for _ in range(max_pages):
        try:
            payload = await client.get(
                f"/api/v3/projects/{project_id}/memberships",
                params={"offset": offset, "pageSize": page_size},
                tool="memberships",
            )
        except OpenProjectHTTPError as exc:
            if exc.status_code == 403:
                raise OpenProjectHTTPError(
                    status_code=403,
                    method="GET",
                    url=f"{client.base_url}/api/v3/projects/{project_id}/memberships",
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

            user = _user_from_membership(m if isinstance(m, dict) else {})
            roles = _roles_from_membership(m if isinstance(m, dict) else {})

            items.append(
                {
                    "membership_id": membership_id,
                    "user_id": user["id"],
                    "user_name": user["name"],
                    "user_href": user["href"],
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
