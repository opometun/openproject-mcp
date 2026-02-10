from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type, TypeVar

from pydantic import BaseModel

from openproject_mcp.client import OpenProjectClient, OpenProjectHTTPError
from openproject_mcp.models import PriorityRef, ProjectRef, StatusRef, TypeRef
from openproject_mcp.tools._collections import embedded_elements

T = TypeVar("T", bound=BaseModel)


# --- Resolution errors ---


class ResolutionError(ValueError):
    def __init__(self, message: str, *, query: str):
        super().__init__(message)
        self.query = query


class AmbiguousResolutionError(ResolutionError):
    def __init__(self, message: str, *, query: str, candidates: list[str]):
        super().__init__(message, query=query)
        self.candidates = candidates


class NotFoundResolutionError(ResolutionError):
    def __init__(self, message: str, *, query: str, available: list[str]):
        super().__init__(message, query=query)
        self.available = available


@dataclass
class _CacheEntry:
    ts: float
    data: List[BaseModel]


_CACHE: Dict[str, _CacheEntry] = {}
DEFAULT_TTL_SECONDS = 600  # 10 minutes


def _cache_key(client: OpenProjectClient, endpoint: str) -> str:
    """
    Cache key includes base_url to isolate multiple client instances.
    """
    return f"{client.base_url}:{endpoint}"


async def _fetch_metadata(
    client: OpenProjectClient,
    endpoint: str,
    model: Type[T],
    *,
    ttl_seconds: float = DEFAULT_TTL_SECONDS,
) -> list[T]:
    """
    Fetch metadata from an endpoint, validate with `model`, and cache the result.
    """
    key = _cache_key(client, endpoint)
    now = time.time()

    entry = _CACHE.get(key)
    if entry and (now - entry.ts) < ttl_seconds:
        return entry.data  # type: ignore[return-value]

    payload = await client.get(endpoint, tool="metadata")
    raw_elements = embedded_elements(payload)

    items: List[T] = [model.model_validate(e) for e in raw_elements]

    _CACHE[key] = _CacheEntry(ts=now, data=items)  # store validated models
    return items


# --- Public list helpers ---


async def list_types(client: OpenProjectClient) -> list[dict[str, Any]]:
    """
    Return minimal list of available Types as dictionaries {id, name}.
    """
    types = await _fetch_metadata(client, "/api/v3/types", TypeRef)
    return [{"id": t.id, "name": t.name} for t in types]


async def list_statuses(client: OpenProjectClient) -> list[dict[str, Any]]:
    """
    Return minimal list of Statuses as dictionaries {id, name, is_closed}.
    """
    statuses = await _fetch_metadata(client, "/api/v3/statuses", StatusRef)
    return [{"id": s.id, "name": s.name, "is_closed": s.is_closed} for s in statuses]


async def list_priorities(client: OpenProjectClient) -> list[dict[str, Any]]:
    """
    Return minimal list of Priorities as dictionaries {id, name}.
    """
    priorities = await _fetch_metadata(client, "/api/v3/priorities", PriorityRef)
    return [{"id": p.id, "name": p.name} for p in priorities]


# --- Project-aware helpers ---


MAX_PROJECT_PAGE_SIZE = 200


async def _resolve_project_id_for_types(
    client: OpenProjectClient, project: int | str
) -> int:
    if isinstance(project, int):
        return project
    if isinstance(project, str) and project.isdigit():
        return int(project)

    payload = await client.get(
        "/api/v3/projects",
        params={"pageSize": MAX_PROJECT_PAGE_SIZE},
        tool="metadata",
    )
    elements = embedded_elements(payload)
    projects: List[ProjectRef] = [ProjectRef.model_validate(e) for e in elements]

    q = _norm(project)

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
    # name contains disambiguation
    matches = [p for p in projects if q in norm(p.name)]
    if len(matches) == 1:
        return matches[0].id
    if len(matches) > 1:
        sorted_matches = sorted(matches, key=lambda p: (norm(p.name), p.id))
        names = [p.name for p in sorted_matches]
        raise AmbiguousResolutionError(
            f"Project '{project}' is ambiguous. Candidates: {', '.join(names)}",
            query=str(project),
            candidates=names,
        )

    available = sorted([p.name for p in projects], key=norm)
    raise NotFoundResolutionError(
        f"Project '{project}' not found. Available: {', '.join(available)}",
        query=str(project),
        available=available,
    )


async def _fetch_project_types(
    client: OpenProjectClient, project_id: int
) -> Optional[list[TypeRef]]:
    try:
        payload = await client.get(
            f"/api/v3/projects/{project_id}/types", tool="metadata"
        )
    except OpenProjectHTTPError as exc:
        if exc.status_code in (404, 405, 501):
            return None  # fall back to global types
        raise

    elements = embedded_elements(payload)
    return [TypeRef.model_validate(e) for e in elements]


# --- Resolve-by-name helpers ---


def _norm(s: str) -> str:
    return s.strip().casefold()


def _sorted_names(items: list[BaseModel]) -> list[str]:
    return sorted([getattr(i, "name", "") for i in items], key=_norm)


def _sorted_items(items: list[BaseModel]) -> list[BaseModel]:
    return sorted(
        items, key=lambda i: (_norm(getattr(i, "name", "")), getattr(i, "id", 0))
    )


def _resolve_from_items(name_query: str, items: list[BaseModel]) -> int:
    q = _norm(name_query)

    # Exact match
    for item in items:
        if _norm(getattr(item, "name", "")) == q:
            return int(item.id)

    # Partial matches
    matches = [i for i in items if q in _norm(getattr(i, "name", ""))]
    if len(matches) == 1:
        return int(matches[0].id)

    if len(matches) > 1:
        sorted_matches = _sorted_items(matches)
        candidates = [f"{i.name} (ID: {i.id})" for i in sorted_matches]
        raise AmbiguousResolutionError(
            f"Ambiguous match for '{name_query}'. "
            f"Found multiple candidates: {', '.join(candidates)}. "
            "Please be more specific.",
            query=name_query,
            candidates=[getattr(i, "name", "") for i in sorted_matches],
        )

    # No match
    available = _sorted_names(items)
    raise NotFoundResolutionError(
        f"Could not find '{name_query}'. Available options: {', '.join(available)}",
        query=name_query,
        available=available,
    )


async def resolve_metadata_id(
    client: OpenProjectClient,
    endpoint: str,
    model: Type[T],
    name_query: str,
) -> int:
    """
    Resolve a metadata item's ID by name.
    - Exact match (case-insensitive) wins.
    - Single substring match is allowed.
    - Multiple substring matches raise an ambiguity error listing candidates.
    """
    items = await _fetch_metadata(client, endpoint, model)
    return _resolve_from_items(name_query, items)


async def resolve_type_id(client: OpenProjectClient, type_name: str) -> int:
    return await resolve_metadata_id(client, "/api/v3/types", TypeRef, type_name)


async def resolve_status_id(client: OpenProjectClient, status_name: str) -> int:
    return await resolve_metadata_id(client, "/api/v3/statuses", StatusRef, status_name)


async def resolve_priority_id(client: OpenProjectClient, priority_name: str) -> int:
    return await resolve_metadata_id(
        client, "/api/v3/priorities", PriorityRef, priority_name
    )


async def resolve_type(client: OpenProjectClient, type_name: str) -> int:
    """
    Alias of resolve_type_id. Returns the type ID for a given name.
    """
    return await resolve_type_id(client, type_name)


async def resolve_status(client: OpenProjectClient, status_name: str) -> int:
    """
    Alias of resolve_status_id. Returns the status ID for a given name.
    """
    return await resolve_status_id(client, status_name)


async def resolve_type_for_project(
    client: OpenProjectClient, project: int | str, type_name: str
) -> int:
    """
    Resolve a type within a project context, honoring project-enabled types.
    Falls back to global types if the project types endpoint is unavailable (404/405/501).
    """  # noqa: E501
    project_id = await _resolve_project_id_for_types(client, project)
    project_types = await _fetch_project_types(client, project_id)
    items: list[BaseModel]
    if project_types is None:
        items = await _fetch_metadata(client, "/api/v3/types", TypeRef)
    else:
        items = project_types
    return _resolve_from_items(type_name, items)
