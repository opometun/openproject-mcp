from __future__ import annotations

from typing import Callable

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from openproject_mcp.transports.http.token_store import (
    TokenStore,
    principal_from_api_key,
)


def _principal_from_request(request: Request):
    principal = getattr(request.state, "auth_principal", None)
    if principal:
        return principal
    # fallback to API key if present
    key = (
        request.headers.get("X-OpenProject-Key")
        or request.headers.get("x-openproject-key")
        or request.headers.get("X-API-Key")
    )
    if key:
        return principal_from_api_key(key)
    return None


def link_routes(store: TokenStore) -> dict[str, Callable]:
    async def link(request: Request) -> Response:
        principal = _principal_from_request(request)
        if not principal:
            return JSONResponse(
                {"error": "unauthorized", "message": "Auth required"},
                status_code=401,
            )
        data = await request.json()
        api_token = data.get("api_token")
        base_url = data.get("base_url")
        if not api_token:
            return JSONResponse(
                {"error": "invalid_request", "message": "api_token required"},
                status_code=400,
            )
        store.set(principal, api_token, base_url)
        return JSONResponse({"status": "ok"}, status_code=200)

    async def unlink(request: Request) -> Response:
        principal = _principal_from_request(request)
        if not principal:
            return JSONResponse(
                {"error": "unauthorized", "message": "Auth required"},
                status_code=401,
            )
        store.delete(principal)
        return JSONResponse({"status": "ok"}, status_code=200)

    return {"/link/openproject": link, "/unlink/openproject": unlink}


__all__ = ["link_routes"]
