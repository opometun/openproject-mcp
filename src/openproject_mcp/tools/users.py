from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from openproject_mcp.client import OpenProjectClient, OpenProjectHTTPError
from openproject_mcp.hal import get_link_href

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
