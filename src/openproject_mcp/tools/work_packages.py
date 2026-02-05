from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from openproject_mcp.client import OpenProjectClient, OpenProjectHTTPError
from openproject_mcp.hal import get_link_href, get_link_title, parse_id_from_href
from openproject_mcp.models import (
    ProjectRef,
    WorkPackage,
    WorkPackageCreateInput,
    WorkPackageUpdateStatusInput,
)
from openproject_mcp.tools._collections import embedded_elements
from openproject_mcp.tools.metadata import (
    list_statuses,
    list_types,
    resolve_priority_id,
    resolve_status_id,
    resolve_type_id,
)

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def _clamp_page_size(page_size: int) -> int:
    return max(1, min(page_size, MAX_PAGE_SIZE))


def _description_raw_to_text(desc: Optional[Dict[str, Any]]) -> str:
    if isinstance(desc, dict):
        raw = desc.get("raw")
        if isinstance(raw, str):
            return raw
    return ""


def _wp_to_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    wp = WorkPackage.model_validate(payload)

    def link(rel: str) -> Dict[str, Optional[Any]]:
        href = get_link_href({"_links": wp.links}, rel)
        return {
            "id": parse_id_from_href(href),
            "name": get_link_title({"_links": wp.links}, rel),
            "href": href,
        }

    status = link("status")
    priority = link("priority")
    project = link("project")
    wp_type = link("type")
    assignee = link("assignee")

    return {
        "id": wp.id,
        "subject": wp.subject,
        "lock_version": wp.lock_version,
        "description": _description_raw_to_text(wp.description),
        "status": {
            "id": status["id"],
            "name": status["name"] or wp.status_title,
        },
        "priority": {
            "id": priority["id"],
            "name": priority["name"] or wp.priority_title,
        },
        "project": {
            "id": project["id"],
            "name": project["name"] or wp.project_title,
        },
        "type": {
            "id": wp_type["id"],
            "name": wp_type["name"],
        },
        "assignee": {
            "id": assignee["id"],
            "name": assignee["name"],
        }
        if assignee["id"] or assignee["name"]
        else None,
        "url": get_link_href({"_links": wp.links}, "self"),
    }


async def _resolve_project_id(client: OpenProjectClient, query: str) -> int:
    """
    Resolve a project by identifier or name (case-insensitive).
    """
    payload = await client.get(
        "/api/v3/projects", params={"pageSize": MAX_PAGE_SIZE}, tool="work_packages"
    )
    elements = embedded_elements(payload)
    projects: List[ProjectRef] = [ProjectRef.model_validate(e) for e in elements]

    q = query.strip().casefold()

    def norm(s: Optional[str]) -> str:
        return (s or "").strip().casefold()

    # identifier exact
    for p in projects:
        if norm(p.identifier) == q:
            return p.id
    # name exact
    for p in projects:
        if norm(p.name) == q:
            return p.id
    # name contains
    matches = [p for p in projects if q in norm(p.name)]
    if len(matches) == 1:
        return matches[0].id
    if len(matches) > 1:
        names = [p.name for p in matches]
        raise ValueError(f"Project '{query}' is ambiguous. Candidates: {names}")

    available = [p.name for p in projects]
    raise ValueError(f"Project '{query}' not found. Available: {available}")


async def get_work_package(client: OpenProjectClient, wp_id: int) -> Dict[str, Any]:
    payload = await client.get(f"/api/v3/work_packages/{wp_id}", tool="work_packages")
    return _wp_to_summary(payload)


async def list_work_packages(
    client: OpenProjectClient,
    *,
    offset: int = 0,
    page_size: int = DEFAULT_PAGE_SIZE,
    project: Optional[str] = None,
    subject_contains: Optional[str] = None,
) -> Dict[str, Any]:
    if offset < 0:
        raise ValueError("offset must be >= 0")
    page_size = _clamp_page_size(page_size)

    params = {"offset": offset, "pageSize": page_size}
    payload = await client.get(
        "/api/v3/work_packages", params=params, tool="work_packages"
    )
    elements = embedded_elements(payload)

    summaries = [_wp_to_summary(e) for e in elements]

    if project:
        project_id = await _resolve_project_id(client, project)
        summaries = [
            s for s in summaries if s.get("project", {}).get("id") == project_id
        ]

    if subject_contains:
        needle = subject_contains.strip().casefold()
        summaries = [s for s in summaries if needle in s.get("subject", "").casefold()]

    total: Optional[int] = (
        payload.get("total") if isinstance(payload.get("total"), int) else None
    )
    if total is None:
        total = len(summaries)

    next_offset: Optional[int] = None
    if isinstance(total, int) and (offset + page_size) < total:
        next_offset = offset + page_size

    return {
        "items": summaries,
        "offset": offset,
        "page_size": page_size,
        "total": total,
        "next_offset": next_offset,
    }


async def create_work_package(
    client: OpenProjectClient, data: WorkPackageCreateInput
) -> Dict[str, Any]:
    project_id = await _resolve_project_id(client, data.project)
    type_id = await resolve_type_id(client, data.type)

    payload: Dict[str, Any] = {
        "subject": data.subject,
        "description": {"raw": data.description or ""},
        "_links": {
            "project": {"href": f"/api/v3/projects/{project_id}"},
            "type": {"href": f"/api/v3/types/{type_id}"},
        },
    }

    if data.priority:
        priority_id = await resolve_priority_id(client, data.priority)
        payload["_links"]["priority"] = {"href": f"/api/v3/priorities/{priority_id}"}

    if data.status:
        status_id = await resolve_status_id(client, data.status)
        payload["_links"]["status"] = {"href": f"/api/v3/statuses/{status_id}"}

    created = await client.post(
        "/api/v3/work_packages", json=payload, tool="work_packages"
    )
    return _wp_to_summary(created)


async def update_status(
    client: OpenProjectClient, data: WorkPackageUpdateStatusInput
) -> Dict[str, Any]:
    current = await client.get(f"/api/v3/work_packages/{data.id}", tool="work_packages")
    lock_version = current.get("lockVersion")
    if lock_version is None:
        raise OpenProjectHTTPError(
            status_code=422,
            method="GET",
            url=f"{client.base_url}/api/v3/work_packages/{data.id}",
            message="lockVersion missing from work package response",
        )

    status_id = await resolve_status_id(client, data.status)
    patch_body = {
        "lockVersion": lock_version,
        "_links": {"status": {"href": f"/api/v3/statuses/{status_id}"}},
    }

    patched = await client.patch(
        f"/api/v3/work_packages/{data.id}", json=patch_body, tool="work_packages"
    )
    return _wp_to_summary(patched)


async def add_comment(
    client: OpenProjectClient, wp_id: int, comment: str
) -> Dict[str, Any]:
    """
    Add a comment to a work package.
    """
    payload = {"comment": {"raw": comment}}
    resp = await client.post(
        f"/api/v3/work_packages/{wp_id}/activities",
        json=payload,
        tool="work_packages",
    )

    return {
        "work_package_id": wp_id,
        "comment": comment,
        "activity_id": parse_id_from_href(get_link_href(resp, "self")),
        "url": get_link_href(resp, "self"),
    }


async def append_work_package_description(
    client: OpenProjectClient, wp_id: int, text: str
) -> Dict[str, Any]:
    """
    Append text to the work package description, preserving lockVersion.
    """
    current = await client.get(f"/api/v3/work_packages/{wp_id}", tool="work_packages")
    lock_version = current.get("lockVersion")
    if lock_version is None:
        raise OpenProjectHTTPError(
            status_code=422,
            method="GET",
            url=f"{client.base_url}/api/v3/work_packages/{wp_id}",
            message="lockVersion missing from work package response",
        )

    existing = _description_raw_to_text(current.get("description"))
    existing = existing.rstrip()
    appended = text if not existing else f"{existing}\n\n{text}"

    patch_body = {
        "lockVersion": lock_version,
        "description": {"raw": appended},
    }

    try:
        updated = await client.patch(
            f"/api/v3/work_packages/{wp_id}",
            json=patch_body,
            tool="work_packages",
        )
    except OpenProjectHTTPError as exc:
        if exc.status_code == 409:
            raise OpenProjectHTTPError(
                status_code=409,
                method="PATCH",
                url=f"{client.base_url}/api/v3/work_packages/{wp_id}",
                message=(
                    "Work package was updated by someone else; "
                    "please reload and retry."
                ),
            ) from exc
        raise

    return _wp_to_summary(updated)


async def search_content(client: OpenProjectClient, query: str) -> Dict[str, Any]:
    """
    Search work packages by text. Tries server-side filter first; falls back to
    client-side filtering of the first page if the server rejects the filter.
    """
    params = {
        "pageSize": MAX_PAGE_SIZE,
        "filters": json.dumps([{"text": {"operator": "~", "values": [query]}}]),
    }

    scope = "server_filtered"
    try:
        payload = await client.get(
            "/api/v3/work_packages", params=params, tool="work_packages"
        )
        elements = embedded_elements(payload)
    except OpenProjectHTTPError as exc:
        if exc.status_code in (400, 415, 422):
            # Fallback: first page, client-side filter
            fallback = await client.get(
                "/api/v3/work_packages",
                params={"pageSize": MAX_PAGE_SIZE},
                tool="work_packages",
            )
            elements = embedded_elements(fallback)
            needle = query.strip().casefold()

            def matches(item: Dict[str, Any]) -> bool:
                subject = str(item.get("subject", "")).casefold()
                desc = _description_raw_to_text(item.get("description")).casefold()
                return needle in subject or needle in desc

            elements = [e for e in elements if matches(e)]
            scope = "client_filtered_first_page"
        else:
            raise

    summaries = [_wp_to_summary(e) for e in elements]
    return {"items": summaries, "scope": scope, "page_size": MAX_PAGE_SIZE}


async def get_work_package_statuses(client: OpenProjectClient) -> list[dict[str, Any]]:
    """
    Expose raw statuses for manual exploration.
    """
    return await list_statuses(client)


async def get_work_package_types(client: OpenProjectClient) -> list[dict[str, Any]]:
    """
    Expose raw types for manual exploration.
    """
    return await list_types(client)
