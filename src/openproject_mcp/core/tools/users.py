from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from openproject_mcp.core.client import OpenProjectClient, OpenProjectHTTPError
from openproject_mcp.core.hal import get_link_href, parse_id_from_href
from openproject_mcp.core.tools._collections import embedded_elements
from openproject_mcp.core.tools.metadata import (
    resolve_project,
)

_CUSTOM_FIELD_RE = re.compile(r"^customField(\d+)$")


def _init_custom_field(key: str, id_part: Optional[str]) -> Dict[str, Any]:
    return {
        "key": key,
        "id": int(id_part) if id_part and id_part.isdigit() else None,
        "value": None,
        "title": None,
        "href": None,
        "links": [],
    }


def _merge_cf_link(cf: Dict[str, Any], item: Any) -> None:
    """Merge a custom field link object into the accumulator."""
    if not isinstance(item, dict):
        return
    entry = {"title": item.get("title"), "href": item.get("href")}
    cf.setdefault("links", []).append(entry)

    if cf.get("title") is None and entry["title"]:
        cf["title"] = entry["title"]
    if cf.get("href") is None and entry["href"]:
        cf["href"] = entry["href"]
    if cf.get("value") is None and entry["title"] is not None:
        cf["value"] = entry["title"]


def _extract_custom_fields(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Collect custom fields from both root properties (customFieldN) and matching
    _links entries. Values are merged per key and ordered by numeric id.
    """

    fields: Dict[str, Dict[str, Any]] = {}

    # Property-based custom fields (e.g., "customField3": "Blue")
    for key, value in payload.items():
        if not isinstance(key, str):
            continue
        match = _CUSTOM_FIELD_RE.match(key)
        if not match:
            continue
        cf = fields.setdefault(key, _init_custom_field(key, match.group(1)))
        cf["value"] = value

    # Link-based custom fields (e.g., "_links": {"customField4": {"title": ...}})
    links = payload.get("_links") if isinstance(payload, dict) else None
    if isinstance(links, dict):
        for key, link_val in links.items():
            if not isinstance(key, str):
                continue
            match = _CUSTOM_FIELD_RE.match(key)
            if not match:
                continue

            cf = fields.setdefault(key, _init_custom_field(key, match.group(1)))

            if isinstance(link_val, list):
                for item in link_val:
                    _merge_cf_link(cf, item)
            else:
                _merge_cf_link(cf, link_val)

    return sorted(
        fields.values(), key=lambda c: ((c.get("id") or 0), c.get("key") or "")
    )


def _user_payload_to_profile(payload: Dict[str, Any]) -> Dict[str, Any]:
    email = None
    if isinstance(payload, dict):
        email = payload.get("mail") or payload.get("email")

    return {
        "id": payload.get("id") if isinstance(payload, dict) else None,
        "name": payload.get("name") if isinstance(payload, dict) else None,
        "login": payload.get("login") if isinstance(payload, dict) else None,
        "status": payload.get("status") if isinstance(payload, dict) else None,
        "email": email,
        "admin": payload.get("admin") if isinstance(payload, dict) else None,
        "created_at": payload.get("createdAt") if isinstance(payload, dict) else None,
        "updated_at": payload.get("updatedAt") if isinstance(payload, dict) else None,
        "last_login": payload.get("lastLogin") if isinstance(payload, dict) else None,
        "href": get_link_href(payload, "self"),
        "custom_fields": _extract_custom_fields(
            payload if isinstance(payload, dict) else {}
        ),
    }


async def get_user_by_id(client: OpenProjectClient, user_id: int) -> Dict[str, Any]:
    """
    Fetch a user by ID, returning email, status, and custom fields when visible.

    Notes:
    - Email may be absent when permissions are limited.
    - Some OpenProject setups return 404 when the user exists but is not visible.
    """

    try:
        payload = await client.get(f"/api/v3/users/{user_id}", tool="users")
    except OpenProjectHTTPError as exc:
        if exc.status_code in (403, 404):
            message = "User not found or insufficient permissions to view this user."
            if exc.status_code == 403:
                message = "Permission denied: unable to view this user."

            raise OpenProjectHTTPError(
                status_code=exc.status_code,
                method="GET",
                url=f"{client.base_url}/api/v3/users/{user_id}",
                message=message,
                response_json=exc.response_json,
                response_text=exc.response_text,
            ) from exc
        raise

    return _user_payload_to_profile(payload)


def _norm_text(val: Optional[str]) -> str:
    if not isinstance(val, str):
        return ""
    return " ".join(val.split()).strip().casefold()


def _match_principal_by_name(name: str, principals: List[Dict[str, Any]]) -> int:
    q = _norm_text(name)
    exact = [p for p in principals if _norm_text(p.get("name")) == q]
    if len(exact) == 1 and exact[0].get("id") is not None:
        return int(exact[0]["id"])
    partial = [p for p in principals if q and q in _norm_text(p.get("name"))]
    if len(partial) == 1 and partial[0].get("id") is not None:
        return int(partial[0]["id"])
    if len(exact) > 1 or len(partial) > 1:
        raise ValueError(
            f"User name '{name}' is ambiguous; please provide a numeric user id."
        )
    raise ValueError(f"User '{name}' not found; provide a numeric user id.")


async def _fetch_membership_principals(
    client: OpenProjectClient, project_id: int
) -> List[Dict[str, Any]]:
    principals: List[Dict[str, Any]] = []
    offset = 0
    page_size = 200
    filters = [
        {"project": {"operator": "=", "values": [str(project_id)]}},
    ]
    while True:
        resp = await client.get(
            "/api/v3/memberships",
            params={
                "offset": offset,
                "pageSize": page_size,
                "filters": json.dumps(filters),
            },
            tool="users",
        )
        batch = embedded_elements(resp)
        for el in batch:
            if not isinstance(el, dict):
                continue
            link = (
                el.get("_links", {}).get("principal", {})
                if isinstance(el.get("_links", {}), dict)
                else {}
            )
            href = link.get("href") if isinstance(link, dict) else None
            name = link.get("title") if isinstance(link, dict) else None
            principals.append(
                {"id": parse_id_from_href(href), "name": name, "href": href}
            )
        if len(batch) < page_size:
            break
        offset += page_size
    return principals


async def get_users(
    client: OpenProjectClient,
    *,
    project: Optional[int | str] = None,
    email_filter: Optional[str] = None,
    offset: int = 0,
    page_size: int = 200,
    max_pages: int = 3,
) -> Dict[str, Any]:
    """
    List visible users. Attempts global listing first (if allowed), otherwise falls back
    to project memberships (when project is provided). Email filter is best-effort and
    may not work if emails are hidden for the token.
    """
    if offset < 0:
        raise ValueError("offset must be >= 0")
    page_size = max(1, min(page_size, 200))

    warnings: List[str] = []
    items: List[Dict[str, Any]] = []
    pages_scanned = 0
    next_offset: Optional[int] = None
    total: Optional[int] = None

    project_id: Optional[int] = None
    if project is not None:
        project_id = await resolve_project(client, project)

    def apply_email_filter(users: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not email_filter:
            return users
        needle = email_filter.strip().casefold()
        filtered = []
        email_seen = False
        for u in users:
            mail = (u.get("email") or u.get("mail") or "") or ""
            if mail:
                email_seen = True
            if mail.casefold().find(needle) != -1:
                filtered.append(u)
        if not email_seen:
            warnings.append(
                "email not visible to this token; email_filter may be ignored and returned no matches."  # noqa: E501
            )
        return filtered

    # Try global listing if no project was provided
    global_failed = False
    if project_id is None:
        try:
            offset_iter = offset
            while pages_scanned < max_pages:
                resp = await client.get(
                    "/api/v3/users",
                    params={"offset": offset_iter, "pageSize": page_size},
                    tool="users",
                )
                batch = embedded_elements(resp)
                pages_scanned += 1
                for el in batch:
                    if not isinstance(el, dict):
                        continue
                    items.append(
                        {
                            "id": el.get("id"),
                            "name": el.get("name"),
                            "login": el.get("login"),
                            "email": el.get("mail") or el.get("email"),
                            "admin": el.get("admin"),
                            "status": el.get("status"),
                        }
                    )
                next_link = get_link_href(resp, "nextByOffset")
                if isinstance(resp, dict) and isinstance(resp.get("total"), int):
                    total = resp.get("total")
                if next_link and pages_scanned < max_pages:
                    offset_iter += page_size
                    continue
                if (
                    next_link is None
                    and isinstance(total, int)
                    and (offset_iter + page_size) < total
                    and pages_scanned < max_pages
                ):
                    offset_iter += page_size
                    continue
                break
            if isinstance(total, int) and (offset_iter + page_size) < total:
                next_offset = offset_iter + page_size
        except OpenProjectHTTPError as exc:
            if exc.status_code in (401, 403, 404):
                global_failed = True
            else:
                raise

    # Fallback to memberships when project provided or global failed
    if (project_id is not None) or (global_failed and project_id is not None):
        try:
            principals = await _fetch_membership_principals(client, project_id)  # type: ignore[arg-type]
            pages_scanned = max(pages_scanned, 1)
            items = [
                {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "login": None,
                    "email": None,
                    "admin": None,
                    "status": None,
                }
                for p in principals
            ]
            total = len(items)
        except OpenProjectHTTPError as exc:
            if exc.status_code not in (401, 403, 404):
                raise
            warnings.append(
                "Membership listing not available; user listing may require a numeric user id or admin token."  # noqa: E501
            )
            if not items:
                raise OpenProjectHTTPError(
                    status_code=exc.status_code,
                    method="GET",
                    url=f"{client.base_url}/api/v3/memberships",
                    message="Cannot list users with this token; provide user ID or project membership.",  # noqa: E501
                    response_json=exc.response_json,
                    response_text=exc.response_text,
                ) from exc

    filtered_items = apply_email_filter(items)

    return {
        "items": filtered_items,
        "offset": offset,
        "page_size": page_size,
        "total": total,
        "next_offset": next_offset,
        "pages_scanned": pages_scanned,
        "warnings": warnings or None,
    }
