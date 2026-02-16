"""Request context and DI contract using ContextVars."""

from __future__ import annotations

import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional

from .client import OpenProjectClient
from .config import load_env_config

# Context variables
_api_key_var: ContextVar[str | None] = ContextVar("api_key", default=None)
_base_url_var: ContextVar[str | None] = ContextVar("base_url", default=None)
_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
_user_agent_var: ContextVar[str | None] = ContextVar("user_agent", default=None)

API_KEY_HEADER = "x-openproject-key"
REQUEST_ID_HEADER = "x-request-id"
USER_AGENT_HEADER = "user-agent"


class MissingApiKeyError(ValueError):
    """Raised when API key is required but missing."""


class MissingBaseUrlError(ValueError):
    """Raised when base URL is required but missing."""


@dataclass(frozen=True)
class RequestContext:
    api_key: str
    base_url: str
    request_id: str
    user_agent: Optional[str] = None


def ensure_request_id(candidate: Optional[str] = None) -> str:
    return candidate or uuid.uuid4().hex


def seed_from_env(*, use_dotenv: bool = False) -> RequestContext:
    base_url, api_key = load_env_config(use_dotenv=use_dotenv)
    if not base_url:
        raise MissingBaseUrlError("OPENPROJECT_BASE_URL not set")
    if not api_key:
        raise MissingApiKeyError("OPENPROJECT_API_KEY not set")
    rid = ensure_request_id(None)
    return RequestContext(
        api_key=api_key, base_url=base_url, request_id=rid, user_agent=None
    )


def seed_from_headers(headers: Mapping[str, str]) -> RequestContext:
    """Extract context hints from HTTP headers (api_key required, base_url not overridden)."""  # noqa: E501
    api_key = headers.get(API_KEY_HEADER)
    base_url_env, api_key_env = load_env_config()
    base_url = base_url_env or None
    if api_key is None:
        api_key = api_key_env or None
    request_id = ensure_request_id(headers.get(REQUEST_ID_HEADER))
    user_agent = headers.get(USER_AGENT_HEADER)
    # Validation deferred to get_context to allow adapters to decide semantics
    return RequestContext(
        api_key=api_key or "",
        base_url=base_url or "",
        request_id=request_id,
        user_agent=user_agent,
    )


def apply_request_context(
    api_key: str,
    base_url: str,
    request_id: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Iterable[Token]:
    """Set ContextVars for the duration of a request; returns tokens for reset()."""
    tokens = []
    tokens.append(_api_key_var.set(api_key))
    tokens.append(_base_url_var.set(base_url))
    tokens.append(_request_id_var.set(ensure_request_id(request_id)))
    tokens.append(_user_agent_var.set(user_agent))
    return tokens


def client_from_context() -> OpenProjectClient:
    ctx = get_context(require_api_key=True, require_base_url=True)
    return OpenProjectClient(base_url=ctx.base_url, api_key=ctx.api_key)


def reset_context(tokens: Iterable[Token]) -> None:
    for token in tokens:
        token.var.reset(token)


def get_context(
    *, require_api_key: bool = True, require_base_url: bool = True
) -> RequestContext:
    api_key = _api_key_var.get()
    base_url = _base_url_var.get()
    request_id = ensure_request_id(_request_id_var.get())
    user_agent = _user_agent_var.get()

    if require_api_key and not api_key:
        raise MissingApiKeyError("API key is required and missing.")
    if require_base_url and not base_url:
        raise MissingBaseUrlError("Base URL is required and missing.")

    return RequestContext(
        api_key=api_key or "",
        base_url=base_url or "",
        request_id=request_id,
        user_agent=user_agent,
    )


__all__ = [
    "RequestContext",
    "MissingApiKeyError",
    "MissingBaseUrlError",
    "seed_from_env",
    "seed_from_headers",
    "get_context",
    "apply_request_context",
    "reset_context",
    "ensure_request_id",
    "client_from_context",
    "API_KEY_HEADER",
    "REQUEST_ID_HEADER",
    "USER_AGENT_HEADER",
]
