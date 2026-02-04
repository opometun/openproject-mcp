from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Type, TypeVar

from pydantic import BaseModel

from openproject_mcp.client import OpenProjectClient
from openproject_mcp.models import PriorityRef, StatusRef, TypeRef
from openproject_mcp.tools._collections import embedded_elements

T = TypeVar("T", bound=BaseModel)


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
) -> List[T]:
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


async def list_types(client: OpenProjectClient) -> List[Dict[str, Any]]:
    """
    Return minimal list of available Types as dictionaries {id, name}.
    """
    types = await _fetch_metadata(client, "/api/v3/types", TypeRef)
    return [{"id": t.id, "name": t.name} for t in types]


async def list_statuses(client: OpenProjectClient) -> List[Dict[str, Any]]:
    """
    Return minimal list of Statuses as dictionaries {id, name, is_closed}.
    """
    statuses = await _fetch_metadata(client, "/api/v3/statuses", StatusRef)
    return [{"id": s.id, "name": s.name, "is_closed": s.is_closed} for s in statuses]


async def list_priorities(client: OpenProjectClient) -> List[Dict[str, Any]]:
    """
    Return minimal list of Priorities as dictionaries {id, name}.
    """
    priorities = await _fetch_metadata(client, "/api/v3/priorities", PriorityRef)
    return [{"id": p.id, "name": p.name} for p in priorities]


# --- Resolve-by-name helpers ---


def _norm(s: str) -> str:
    return s.strip().casefold()


async def resolve_metadata_id(
    client: OpenProjectClient,
    endpoint: str,
    model: Type[T],
    name_query: str,
) -> int:
    """
    Resolve a metadata item's ID by name.
    Exact match (case-insensitive) first, then substring fallback.
    """
    items = await _fetch_metadata(client, endpoint, model)
    q = _norm(name_query)

    for item in items:
        if _norm(getattr(item, "name", "")) == q:
            return int(item.id)

    for item in items:
        if q in _norm(getattr(item, "name", "")):
            return int(item.id)

    available = [getattr(i, "name", "") for i in items]
    raise ValueError(f"'{name_query}' not found. Available: {available}")


async def resolve_type_id(client: OpenProjectClient, type_name: str) -> int:
    return await resolve_metadata_id(client, "/api/v3/types", TypeRef, type_name)


async def resolve_status_id(client: OpenProjectClient, status_name: str) -> int:
    return await resolve_metadata_id(client, "/api/v3/statuses", StatusRef, status_name)


async def resolve_priority_id(client: OpenProjectClient, priority_name: str) -> int:
    return await resolve_metadata_id(
        client, "/api/v3/priorities", PriorityRef, priority_name
    )
