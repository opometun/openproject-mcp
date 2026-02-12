from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Dict, List, Optional

from openproject_mcp.client import OpenProjectClient, OpenProjectHTTPError
from openproject_mcp.hal import parse_id_from_href
from openproject_mcp.tools._collections import embedded_elements
from openproject_mcp.tools.metadata import (
    NotFoundResolutionError,
    resolve_project,
    resolve_user,
)
from openproject_mcp.utils.time_parser import DurationParseError, parse_duration_string


async def log_time(
    client: OpenProjectClient,
    work_package_id: int,
    duration: str,
    comment: str = "",
    activity_id: int = 1,
    spent_on: Optional[date] = None,
) -> str:
    """
    Log time on a work package.

    Args:
        work_package_id: Target work package ID.
        duration: Human string like "2h", "30m", "2h 30m".
        comment: Optional comment.
        activity_id: Activity to assign; Stage 1 assumes caller provides a valid ID.
        spent_on: Date; defaults to today.

    Returns:
        Success message with work package id and original duration string.
    """
    try:
        iso_duration = parse_duration_string(duration)
    except DurationParseError as exc:
        return (
            f"Error: {exc} Accepted examples: '2h', '30m', '2h 30m'. "
            "Use hours (h) and minutes (m)."
        )

    spent_on_value = (spent_on or date.today()).isoformat()

    payload: Dict[str, Any] = {
        "hours": iso_duration,
        "comment": {"raw": comment},
        "spentOn": spent_on_value,
        "_links": {
            "entity": {"href": f"/api/v3/work_packages/{work_package_id}"},
            "activity": {"href": f"/api/v3/time_entries/activities/{activity_id}"},
        },
    }

    await client.post("/api/v3/time_entries", json=payload, tool="time_entries")
    return f"Logged {duration} to work package {work_package_id} on {spent_on_value}."


def _parse_iso_duration_to_minutes(iso: str) -> Optional[int]:
    """
    Parse a simple ISO-8601 duration like PT2H30M into total minutes.
    Returns None if parsing fails or unsupported format.
    """
    if not isinstance(iso, str):
        return None
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 60 + minutes + (1 if seconds and seconds > 0 else 0)


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


async def _fetch_project_membership_principals(
    client: OpenProjectClient, project_id: int
) -> List[Dict[str, Any]]:
    principals: List[Dict[str, Any]] = []
    offset = 0
    page_size = 200
    filters = json.dumps([{"project": {"operator": "=", "values": [str(project_id)]}}])
    while True:
        resp = await client.get(
            "/api/v3/memberships",
            params={"offset": offset, "pageSize": page_size, "filters": filters},
            tool="time_entries",
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
            title = link.get("title") if isinstance(link, dict) else None
            principals.append({"id": parse_id_from_href(href), "name": title})
        if len(batch) < page_size:
            break
        offset += page_size
    return principals


async def _resolve_user_id(
    client: OpenProjectClient, user: Optional[Any], project_id: Optional[int]
) -> int:
    """
    Resolve user parameter to user id with permission-resilient fallbacks.
    - None or "me" -> current user
    - int or numeric string -> treated as id
    - otherwise -> try project memberships (if project_id provided), then /users
      If resolution is blocked by permissions, raise a clear guidance error.
    """
    if user is None or (isinstance(user, str) and user.strip().lower() == "me"):
        me = await client.get("/api/v3/users/me", tool="time_entries")
        if "id" not in me:
            raise NotFoundResolutionError(
                "Could not resolve current user id", query="me", available=[]
            )
        return int(me["id"])

    if isinstance(user, int):
        return user
    if isinstance(user, str) and user.strip().isdigit():
        return int(user.strip())

    name = str(user)

    # Project-scoped memberships first (if project provided)
    if project_id is not None:
        try:
            principals = await _fetch_project_membership_principals(client, project_id)
            if principals:
                return _match_principal_by_name(name, principals)
        except OpenProjectHTTPError as exc:
            if exc.status_code not in (401, 403, 404):
                raise
            # fall through to global resolver / final error

    # Global resolver as final attempt
    try:
        return await resolve_user(client, name)
    except OpenProjectHTTPError as exc:
        if exc.status_code in (401, 403, 404):
            raise NotFoundResolutionError(
                "Cannot resolve user by name; provide numeric user id or 'me' (user listing not permitted).",  # noqa: E501
                query=name,
                available=[],
            ) from exc
        raise
    except Exception as exc:
        # Catch ResolutionError or other resolver issues and surface a guidance error
        raise NotFoundResolutionError(
            "Cannot resolve user by name; provide numeric user id or 'me' (user listing not permitted).",  # noqa: E501
            query=name,
            available=[],
        ) from exc
    except NotFoundResolutionError:
        raise
    except ValueError:
        raise


async def _build_filters(
    client: OpenProjectClient,
    user: Optional[Any],
    project: Optional[Any],
    work_package: Optional[int],
    spent_from: Optional[Any],
    spent_to: Optional[Any],
) -> List[Dict[str, Any]]:
    filters: List[Dict[str, Any]] = []

    project_id: Optional[int] = None
    if project is not None:
        project_id = await resolve_project(client, project)
        filters.append({"project": {"operator": "=", "values": [str(project_id)]}})

    user_id = await _resolve_user_id(client, user, project_id)
    filters.append({"user": {"operator": "=", "values": [str(user_id)]}})

    if work_package is not None:
        filters.append(
            {"workPackage": {"operator": "=", "values": [str(work_package)]}}
        )

    def to_date_str(val: Any) -> str:
        if isinstance(val, date):
            return val.isoformat()
        return str(val)

    if spent_from is not None:
        filters.append(
            {"spentOn": {"operator": ">=", "values": [to_date_str(spent_from)]}}
        )
    if spent_to is not None:
        filters.append(
            {"spentOn": {"operator": "<=", "values": [to_date_str(spent_to)]}}
        )

    return filters


async def list_time_entries(
    client: OpenProjectClient,
    *,
    user: Optional[Any] = None,
    project: Optional[Any] = None,
    work_package: Optional[int] = None,
    spent_from: Optional[Any] = None,
    spent_to: Optional[Any] = None,
    offset: int = 0,
    page_size: int = 50,
) -> Dict[str, Any]:
    """
    List time entries. Defaults to the current user's time when no user is provided.
    Filters: user, project, work_package, spent_from (>=), spent_to (<=).
    """
    if offset < 0:
        raise ValueError("offset must be >= 0")
    page_size = max(1, min(page_size, 200))

    filters = await _build_filters(
        client, user, project, work_package, spent_from, spent_to
    )

    payload = await client.get(
        "/api/v3/time_entries",
        params={
            "offset": offset,
            "pageSize": page_size,
            "filters": json.dumps(filters),
        },
        tool="time_entries",
    )

    elements = embedded_elements(payload)
    items: List[Dict[str, Any]] = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        hours_iso = el.get("hours")
        minutes_total = _parse_iso_duration_to_minutes(hours_iso)
        hours_decimal = (
            round(minutes_total / 60, 2) if minutes_total is not None else None
        )
        comment = ""
        if isinstance(el.get("comment"), dict):
            comment = el.get("comment", {}).get("raw") or ""
        user_link = (
            el.get("_links", {}).get("user", {})
            if isinstance(el.get("_links", {}), dict)
            else {}
        )
        proj_link = (
            el.get("_links", {}).get("project", {})
            if isinstance(el.get("_links", {}), dict)
            else {}
        )
        wp_link = (
            el.get("_links", {}).get("workPackage", {})
            if isinstance(el.get("_links", {}), dict)
            else {}
        )

        def _link_info(link: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "id": parse_id_from_href(link.get("href"))
                if isinstance(link, dict)
                else None,
                "name": link.get("title") if isinstance(link, dict) else None,
            }

        items.append(
            {
                "id": el.get("id"),
                "hours_iso": hours_iso,
                "hours_decimal": hours_decimal,
                "minutes": minutes_total,
                "spent_on": el.get("spentOn"),
                "comment": comment,
                "user": _link_info(user_link),
                "project": _link_info(proj_link),
                "work_package": _link_info(wp_link),
            }
        )

    total = payload.get("total") if isinstance(payload, dict) else None
    next_offset = None
    if isinstance(total, int) and (offset + page_size) < total:
        next_offset = offset + page_size

    return {
        "items": items,
        "offset": offset,
        "page_size": page_size,
        "total": total if isinstance(total, int) else None,
        "next_offset": next_offset,
    }


async def get_my_logged_time(
    client: OpenProjectClient, **kwargs: Any
) -> Dict[str, Any]:
    """
    Deprecated: use list_time_entries(user=\"me\", ...) instead.
    """
    return await list_time_entries(client, user="me", **kwargs)
