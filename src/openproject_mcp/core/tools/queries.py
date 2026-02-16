from __future__ import annotations

import json
from typing import Any, Dict, Optional

from openproject_mcp.core.client import OpenProjectClient, OpenProjectHTTPError
from openproject_mcp.core.hal import get_link_href, parse_id_from_href
from openproject_mcp.core.tools._collections import embedded_elements
from openproject_mcp.core.tools.work_packages import _clamp_page_size, _wp_to_summary


def _compute_next_offset(
    *,
    total: Optional[int],
    page_size: Optional[int],
    offset: Optional[int],
    count: Optional[int],
) -> Optional[int]:
    """
    Derive the next offset/page number using the paging fields returned by the API.
    Works with query results where offset is a page number (per OpenProject docs).
    """
    if (
        not isinstance(total, int)
        or not isinstance(page_size, int)
        or not isinstance(offset, int)
    ):
        return None

    # When offset is a page number: advance while there is remaining data.
    if (offset * page_size) < total:
        return offset + 1

    # Fallback using count if provided
    if isinstance(count, int) and ((offset - 1) * page_size + count) < total:
        return offset + 1

    return None


def _query_to_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    project_href = get_link_href({"_links": payload.get("_links", {})}, "project")
    return {
        "id": payload.get("id"),
        "name": payload.get("name"),
        "href": get_link_href({"_links": payload.get("_links", {})}, "self"),
        "project_id": parse_id_from_href(project_href),
        "public": payload.get("public"),
        "starred": payload.get("starred"),
    }


async def list_queries(
    client: OpenProjectClient,
    *,
    project_id: Optional[int] = None,
    offset: int = 0,
    page_size: int = 50,
) -> Dict[str, Any]:
    """
    List saved queries (views). Optional project filter by ID.
    """
    page_size = _clamp_page_size(page_size)

    params: Dict[str, Any] = {"offset": offset, "pageSize": page_size}
    if project_id is not None:
        filters = [{"project_id": {"operator": "=", "values": [str(project_id)]}}]
        params["filters"] = json.dumps(filters)

    payload = await client.get("/api/v3/queries", params=params, tool="queries")

    elements = embedded_elements(payload)
    items = [_query_to_summary(e) for e in elements]

    total = payload.get("total") if isinstance(payload, dict) else None
    total_int = total if isinstance(total, int) else None
    page_size_val = (
        payload.get("pageSize")
        if isinstance(payload.get("pageSize"), int)
        else page_size
    )
    offset_val = (
        payload.get("offset") if isinstance(payload.get("offset"), int) else offset
    )
    count_val = (
        payload.get("count") if isinstance(payload.get("count"), int) else len(items)
    )

    next_offset = _compute_next_offset(
        total=total_int, page_size=page_size_val, offset=offset_val, count=count_val
    )

    return {
        "items": items,
        "total": total_int,
        "offset": offset_val,
        "page_size": page_size_val,
        "count": count_val,
        "next_offset": next_offset,
    }


async def run_query(
    client: OpenProjectClient, query_id: int, *, offset: int = 1, page_size: int = 50
) -> Dict[str, Any]:
    """
    Execute a saved query (View) and return matching work packages.

    Note: For query results, 'offset' is treated as a page number (OpenProject API).
    """
    page_size = _clamp_page_size(page_size)

    try:
        payload = await client.get(
            f"/api/v3/queries/{query_id}",
            params={"offset": offset, "pageSize": page_size},
            tool="queries",
        )
    except OpenProjectHTTPError as exc:
        if exc.status_code == 404:
            raise OpenProjectHTTPError(
                status_code=404,
                method="GET",
                url=f"{client.base_url}/api/v3/queries/{query_id}",
                message="Query not found.",
                response_json=exc.response_json,
                response_text=exc.response_text,
            ) from exc
        raise

    results = (
        payload.get("_embedded", {}).get("results", {})
        if isinstance(payload, dict)
        else {}
    )
    elements = (
        results.get("_embedded", {}).get("elements", [])
        if isinstance(results, dict)
        else []
    )
    items = [_wp_to_summary(e) for e in elements if isinstance(e, dict)]

    total = results.get("total") if isinstance(results, dict) else None
    count = results.get("count") if isinstance(results, dict) else None
    page_size_val = (
        results.get("pageSize")
        if isinstance(results.get("pageSize"), int)
        else page_size
    )
    offset_val = (
        results.get("offset") if isinstance(results.get("offset"), int) else offset
    )

    next_offset = _compute_next_offset(
        total=total if isinstance(total, int) else None,
        page_size=page_size_val,
        offset=offset_val,
        count=count if isinstance(count, int) else len(items),
    )

    return {
        "query_id": query_id,
        "items": items,
        "total": total if isinstance(total, int) else None,
        "count": count if isinstance(count, int) else len(items),
        "page_size": page_size_val,
        "offset": offset_val,
        "next_offset": next_offset,
    }
