from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from openproject_mcp.client import OpenProjectClient, OpenProjectHTTPError
from openproject_mcp.hal import get_link_href, get_link_title, parse_id_from_href
from openproject_mcp.models import (
    ProjectRef,
    WorkPackage,
    WorkPackageCreateInput,
    WorkPackageUpdateInput,
    WorkPackageUpdateStatusInput,
)
from openproject_mcp.tools._collections import embedded_elements
from openproject_mcp.tools.metadata import (
    list_statuses,
    list_types,
    resolve_priority_id,
    resolve_status_id,
    resolve_type_for_project,
    resolve_type_id,
    resolve_user,
)
from openproject_mcp.utils.time_parser import DurationParseError, parse_duration_string

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


def _norm_text(val: Optional[str]) -> str:
    if not isinstance(val, str):
        return ""
    # collapse internal whitespace for resilient matching
    return " ".join(val.split()).strip().casefold()


def _collect_available_assignees(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    elements = embedded_elements(payload)
    principals: List[Dict[str, Any]] = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        name = el.get("name") or el.get("fullName")
        href = get_link_href(el, "self") or el.get("_links", {}).get("self", {}).get(
            "href"
        )
        principal_id = parse_id_from_href(href) or el.get("id")
        principals.append(
            {
                "id": principal_id,
                "name": name,
                "href": href,
                "login": el.get("login"),
                "mail": el.get("mail"),
            }
        )
    return principals


def _collect_membership_principals(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    elements = embedded_elements(payload)
    principals: List[Dict[str, Any]] = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        principal_link = el.get("_links", {}).get("principal", {})
        name = principal_link.get("title")
        href = principal_link.get("href")
        principal_id = parse_id_from_href(href)
        principals.append({"id": principal_id, "name": name, "href": href})
    return principals


def _match_principal(name_query: str, principals: List[Dict[str, Any]]) -> int:
    q = _norm_text(name_query)
    exact = [p for p in principals if _norm_text(p.get("name")) == q]
    if len(exact) == 1 and exact[0].get("id") is not None:
        return int(exact[0]["id"])
    # partial matches
    partial = [p for p in principals if q and q in _norm_text(p.get("name"))]
    if len(partial) == 1 and partial[0].get("id") is not None:
        return int(partial[0]["id"])
    if len(exact) > 1 or len(partial) > 1:
        raise ValueError(
            f"Name '{name_query}' is ambiguous; please specify a numeric user id."
        )
    raise ValueError(f"User '{name_query}' not found; provide a numeric user id.")


def _match_version(name_query: str, versions: List[Dict[str, Any]]) -> int:
    q = _norm_text(name_query)
    exact = [v for v in versions if _norm_text(v.get("name")) == q]
    if len(exact) == 1 and exact[0].get("id") is not None:
        return int(exact[0]["id"])

    contains = [v for v in versions if q and q in _norm_text(v.get("name"))]
    if len(contains) == 1 and contains[0].get("id") is not None:
        return int(contains[0]["id"])

    if len(exact) > 1 or len(contains) > 1:
        raise ValueError(
            f"Version name '{name_query}' is ambiguous; please provide a numeric version id."  # noqa: E501
        )
    raise ValueError(f"Version '{name_query}' not found; provide a numeric version id.")


async def _fetch_available_assignees_list(
    client: OpenProjectClient, wp_payload: Dict[str, Any]
) -> Optional[List[Dict[str, Any]]]:
    href = get_link_href(wp_payload, "availableAssignees")
    if not href:
        return None

    principals: List[Dict[str, Any]] = []
    offset = 1
    while True:
        resp = await client.get(href, params={"offset": offset}, tool="work_packages")
        principals.extend(_collect_available_assignees(resp))
        total = resp.get("total") if isinstance(resp, dict) else None
        page_size = resp.get("pageSize") if isinstance(resp, dict) else None
        if not (isinstance(total, int) and isinstance(page_size, int)):
            break
        if offset * page_size >= total:
            break
        offset += 1

    return principals


async def _fetch_project_membership_principals(
    client: OpenProjectClient, project_id: int
) -> List[Dict[str, Any]]:
    principals: List[Dict[str, Any]] = []
    offset = 0
    page_size = MAX_PAGE_SIZE
    filters = json.dumps([{"project": {"operator": "=", "values": [str(project_id)]}}])

    while True:
        resp = await client.get(
            "/api/v3/memberships",
            params={"offset": offset, "pageSize": page_size, "filters": filters},
            tool="work_packages",
        )
        principals.extend(_collect_membership_principals(resp))
        batch = embedded_elements(resp)
        if len(batch) < page_size:
            break
        offset += page_size

    return principals


async def _fetch_project_versions(
    client: OpenProjectClient, project_id: int
) -> List[Dict[str, Any]]:
    versions: List[Dict[str, Any]] = []
    offset = 0
    page_size = MAX_PAGE_SIZE
    while True:
        resp = await client.get(
            f"/api/v3/projects/{project_id}/versions",
            params={"offset": offset, "pageSize": page_size},
            tool="work_packages",
        )
        versions.extend(
            [
                {"id": v.get("id"), "name": v.get("name")}
                for v in embedded_elements(resp)
                if isinstance(v, dict)
            ]
        )
        batch = embedded_elements(resp)
        if len(batch) < page_size:
            break
        offset += page_size
    return versions


async def _resolve_version_for_wp(
    client: OpenProjectClient,
    wp_payload: Dict[str, Any],
    version_value: Any,
) -> int:
    # numeric fast path
    if isinstance(version_value, int):
        return version_value
    if isinstance(version_value, str) and version_value.strip().isdigit():
        return int(version_value.strip())

    project_href = get_link_href(wp_payload, "project")
    project_id = parse_id_from_href(project_href) if project_href else None
    if project_id is None:
        raise ValueError("Cannot resolve version: work package project is unknown.")

    try:
        versions = await _fetch_project_versions(client, project_id)
    except OpenProjectHTTPError as exc:
        if exc.status_code in (403, 404):
            raise OpenProjectHTTPError(
                status_code=exc.status_code,
                method="GET",
                url=f"{client.base_url}/api/v3/projects/{project_id}/versions",
                message="Version list unavailable for this project; provide a numeric version id or check permissions.",  # noqa: E501
                response_json=exc.response_json,
                response_text=exc.response_text,
            ) from exc
        raise

    return _match_version(str(version_value), versions)


async def _resolve_principal_for_wp(
    client: OpenProjectClient,
    name_or_id: Any,
    wp_payload: Dict[str, Any],
) -> int:
    # Fast path for numeric
    if isinstance(name_or_id, str) and name_or_id.strip().isdigit():
        return int(name_or_id.strip())
    if isinstance(name_or_id, int):
        return name_or_id

    # Try available assignees
    try:
        avail = await _fetch_available_assignees_list(client, wp_payload)
    except OpenProjectHTTPError as exc:
        if exc.status_code not in (403, 404):
            raise
        avail = None

    if avail:
        try:
            return _match_principal(name_or_id, avail)
        except ValueError:
            # Fall through to memberships or final error
            pass

    # Fallback to memberships if we have a project
    project_href = get_link_href(wp_payload, "project")
    project_id = parse_id_from_href(project_href) if project_href else None
    if project_id is not None:
        try:
            principals = await _fetch_project_membership_principals(client, project_id)
            if principals:
                return _match_principal(name_or_id, principals)
        except OpenProjectHTTPError as exc:
            if exc.status_code not in (403, 404):
                raise

    # Final fallback: global resolver (may fail if permissions insufficient)
    return await resolve_user(client, name_or_id)


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
    """Fetch a work package by ID and return a concise summary."""
    payload = await client.get(f"/api/v3/work_packages/{wp_id}", tool="work_packages")
    return _wp_to_summary(payload)


async def list_work_packages(
    client: OpenProjectClient,
    *,
    offset: int = 0,
    page_size: int = DEFAULT_PAGE_SIZE,
    project: Optional[str] = None,
    subject_contains: Optional[str] = None,
    max_pages: int = 5,
) -> Dict[str, Any]:
    """List work packages with optional project/subject filtering and pagination."""
    if offset < 0:
        raise ValueError("offset must be >= 0")
    page_size = _clamp_page_size(page_size)

    # Build server-side filters
    filters = []
    if project:
        project_id = await _resolve_project_id(client, project)
        filters.append({"project": {"operator": "=", "values": [str(project_id)]}})
    if subject_contains:
        filters.append({"text": {"operator": "~", "values": [subject_contains]}})

    params = {"pageSize": page_size}
    if filters:
        params["filters"] = json.dumps(filters)

    items: List[Dict[str, Any]] = []
    pages_scanned = 0
    next_link: Optional[str] = None
    current_offset = offset

    while pages_scanned < max_pages:
        if next_link:
            payload = await client.get(next_link, tool="work_packages")
        else:
            payload = await client.get(
                "/api/v3/work_packages",
                params={**params, "offset": current_offset},
                tool="work_packages",
            )

        elements = embedded_elements(payload)
        items.extend([_wp_to_summary(e) for e in elements])
        pages_scanned += 1

        # HAL next link if present
        next_link = get_link_href(payload, "nextByOffset")
        total = payload.get("total") if isinstance(payload, dict) else None
        page_size_payload = (
            payload.get("pageSize") if isinstance(payload, dict) else None
        )
        if (
            next_link is None
            and isinstance(total, int)
            and isinstance(page_size_payload, int)
        ):
            if (current_offset + page_size_payload) < total:
                current_offset += page_size_payload
                continue
        if next_link is None:
            break

    return {
        "items": items,
        "offset": offset,
        "page_size": page_size,
        "total": payload.get("total") if isinstance(payload, dict) else len(items),
        "next_offset": current_offset + page_size if next_link else None,
        "pages_scanned": pages_scanned,
    }


async def create_work_package(
    client: OpenProjectClient, data: WorkPackageCreateInput
) -> Dict[str, Any]:
    """Create a work package with subject, description, type, project, priority, and status."""  # noqa: E501
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
    """Update a work package's status by name, handling lockVersion for concurrency."""
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


async def update_work_package(
    client: OpenProjectClient, data: WorkPackageUpdateInput
) -> Dict[str, Any]:
    """
    Update multiple attributes of a work package in a single call.
    Supports subject, description (replace or append), status, priority, assignee,
    responsible/accountable, version, start/due dates, percentage done, estimated time,
    type, and project.
    Only provided fields are changed; others are left untouched.
    """
    if data.description is not None and data.append_description is not None:
        raise ValueError("Provide either description or append_description, not both.")

    current = await client.get(f"/api/v3/work_packages/{data.id}", tool="work_packages")
    lock_version = current.get("lockVersion")
    if lock_version is None:
        raise OpenProjectHTTPError(
            status_code=422,
            method="GET",
            url=f"{client.base_url}/api/v3/work_packages/{data.id}",
            message="lockVersion missing from work package response",
        )

    payload: Dict[str, Any] = {"lockVersion": lock_version}
    links: Dict[str, Any] = {}

    if data.subject is not None:
        payload["subject"] = data.subject

    if data.description is not None:
        payload["description"] = {"raw": data.description}
    elif data.append_description is not None:
        existing = _description_raw_to_text(current.get("description"))
        existing = existing.rstrip()
        combined = (
            data.append_description
            if not existing
            else f"{existing}\n\n{data.append_description}"
        )
        payload["description"] = {"raw": combined}

    if data.start_date is not None:
        payload["startDate"] = (
            data.start_date.isoformat()
            if hasattr(data.start_date, "isoformat")
            else str(data.start_date)
        )
    if data.due_date is not None:
        payload["dueDate"] = (
            data.due_date.isoformat()
            if hasattr(data.due_date, "isoformat")
            else str(data.due_date)
        )

    if data.percent_done is not None:
        if not (0 <= data.percent_done <= 100):
            raise ValueError("percent_done must be between 0 and 100.")
        payload["percentageDone"] = data.percent_done

    if data.estimated_time is not None:
        iso_duration = data.estimated_time
        if not (isinstance(iso_duration, str) and iso_duration.startswith("PT")):
            try:
                iso_duration = parse_duration_string(str(data.estimated_time))
            except DurationParseError as exc:
                raise ValueError(str(exc)) from exc
        payload["estimatedTime"] = iso_duration

    # Resolve links
    if data.status is not None:
        status_id = await resolve_status_id(client, data.status)
        links["status"] = {"href": f"/api/v3/statuses/{status_id}"}

    if data.priority is not None:
        priority_id = await resolve_priority_id(client, data.priority)
        links["priority"] = {"href": f"/api/v3/priorities/{priority_id}"}

    # Version: only act if provided; None clears; name resolves within project
    if "version" in data.model_fields_set:
        if data.version is None:
            links["version"] = {"href": None}
        else:
            # Check writable link presence
            if "version" not in current.get("_links", {}):
                raise ValueError(
                    "Version is not writable for this work package; please check project/type settings."  # noqa: E501
                )
            version_id = await _resolve_version_for_wp(client, current, data.version)
            links["version"] = {"href": f"/api/v3/versions/{version_id}"}

    # Resolve assignee: only act if the field was provided; None clears
    if "assignee" in data.model_fields_set:
        if data.assignee is None:
            links["assignee"] = {"href": None}
        else:
            assignee_id = await _resolve_principal_for_wp(
                client, data.assignee, current
            )
            links["assignee"] = {"href": f"/api/v3/users/{assignee_id}"}

    # Resolve responsible/accountable: only act if provided; None clears
    if "accountable" in data.model_fields_set:
        if data.accountable is None:
            links["responsible"] = {"href": None}
        else:
            responsible_id = await _resolve_principal_for_wp(
                client, data.accountable, current
            )
            links["responsible"] = {"href": f"/api/v3/users/{responsible_id}"}

    # Resolve type with project context when possible
    if data.type is not None:
        project_href = get_link_href(current, "project")
        project_id = parse_id_from_href(project_href)
        try:
            if project_id is not None:
                type_id = await resolve_type_for_project(client, project_id, data.type)
            else:
                type_id = await resolve_type_id(client, data.type)
        except Exception:
            type_id = await resolve_type_id(client, data.type)
        links["type"] = {"href": f"/api/v3/types/{type_id}"}

    if data.project is not None:
        project_id = await _resolve_project_id(client, data.project)
        links["project"] = {"href": f"/api/v3/projects/{project_id}"}

    if links:
        payload["_links"] = links

    try:
        patched = await client.patch(
            f"/api/v3/work_packages/{data.id}", json=payload, tool="work_packages"
        )
    except OpenProjectHTTPError as exc:
        if exc.status_code == 409:
            raise OpenProjectHTTPError(
                status_code=409,
                method="PATCH",
                url=f"{client.base_url}/api/v3/work_packages/{data.id}",
                message="Update conflict: lockVersion is outdated. Re-fetch and retry.",
                response_json=exc.response_json,
                response_text=exc.response_text,
            ) from exc
        if exc.status_code == 422:
            message = "Validation failed."
            if isinstance(exc.response_json, dict):
                errors = (
                    exc.response_json.get("_embedded", {}).get("errors", [])
                    if isinstance(exc.response_json.get("_embedded", {}), dict)
                    else []
                )
                messages = [
                    e.get("message")
                    for e in errors
                    if isinstance(e, dict) and e.get("message")
                ]
                if messages:
                    message = "Validation failed: " + "; ".join(messages)
                elif exc.response_json.get("message"):
                    message = exc.response_json.get("message")
            raise OpenProjectHTTPError(
                status_code=422,
                method="PATCH",
                url=f"{client.base_url}/api/v3/work_packages/{data.id}",
                message=message,
                response_json=exc.response_json,
                response_text=exc.response_text,
            ) from exc
        raise

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
    client-side filtering with pagination if the server rejects the filter.
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
            # Fallback: paginate and filter client-side on subject/description
            scope = "client_filtered_paginated"
            elements = []
            offset = 0
            page_size = MAX_PAGE_SIZE
            pages_scanned = 0
            needle = query.strip().casefold()
            while pages_scanned < 5:  # limit fallback scanning
                fallback = await client.get(
                    "/api/v3/work_packages",
                    params={"pageSize": page_size, "offset": offset},
                    tool="work_packages",
                )
                batch = embedded_elements(fallback)

                def matches(item: Dict[str, Any], *, _needle: str = needle) -> bool:
                    subject = str(item.get("subject", "")).casefold()
                    desc = _description_raw_to_text(item.get("description")).casefold()
                    return _needle in subject or _needle in desc

                elements.extend([e for e in batch if matches(e)])

                total = fallback.get("total") if isinstance(fallback, dict) else None
                page_size_payload = (
                    fallback.get("pageSize") if isinstance(fallback, dict) else None
                )
                next_link = get_link_href(fallback, "nextByOffset")
                pages_scanned += 1
                if next_link:
                    offset += (
                        page_size_payload
                        if isinstance(page_size_payload, int)
                        else page_size
                    )
                    continue
                if isinstance(total, int) and isinstance(page_size_payload, int):
                    if (offset + page_size_payload) < total:
                        offset += page_size_payload
                        continue
                break
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


async def list_work_package_versions(
    client: OpenProjectClient, wp_id: int
) -> Dict[str, Any]:
    """
    List available Versions for the work package's project.
    Raises a clear error if the field is not writable or versions are unavailable.
    """
    wp = await client.get(f"/api/v3/work_packages/{wp_id}", tool="work_packages")
    project_href = get_link_href(wp, "project")
    if not project_href:
        raise OpenProjectHTTPError(
            status_code=422,
            method="GET",
            url=f"{client.base_url}/api/v3/work_packages/{wp_id}",
            message="Cannot list versions: work package project is unknown.",
        )

    # If version link is missing, treat as not writable/hidden
    if "version" not in wp.get("_links", {}):
        raise OpenProjectHTTPError(
            status_code=422,
            method="GET",
            url=f"{client.base_url}/api/v3/work_packages/{wp_id}",
            message="Version field is not available for this work package.",
        )

    project_id = parse_id_from_href(project_href)
    if project_id is None:
        raise OpenProjectHTTPError(
            status_code=422,
            method="GET",
            url=f"{client.base_url}/api/v3/work_packages/{wp_id}",
            message="Cannot list versions: project id is missing.",
        )

    versions: List[Dict[str, Any]] = []
    offset = 0
    page_size = MAX_PAGE_SIZE
    while True:
        try:
            resp = await client.get(
                f"/api/v3/projects/{project_id}/versions",
                params={"offset": offset, "pageSize": page_size},
                tool="work_packages",
            )
        except OpenProjectHTTPError as exc:
            if exc.status_code in (403, 404):
                raise OpenProjectHTTPError(
                    status_code=exc.status_code,
                    method="GET",
                    url=f"{client.base_url}/api/v3/projects/{project_id}/versions",
                    message="Unable to list versions for this project; check permissions or project versions configuration.",  # noqa: E501
                    response_json=exc.response_json,
                    response_text=exc.response_text,
                ) from exc
            raise

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

    return {
        "items": versions,
        "total": len(versions),
        "project_id": project_id,
        "work_package_id": wp_id,
    }
