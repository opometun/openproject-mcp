from __future__ import annotations

import json
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from openproject_mcp.core.config import load_env_config
from openproject_mcp.core.context import (
    REQUEST_ID_HEADER,
    MissingApiKeyError,
    MissingBaseUrlError,
    apply_request_context,
    extract_api_key,
    get_context,
    reset_context,
)
from openproject_mcp.transports.http.errors import TokenNotLinkedError
from openproject_mcp.transports.http.op_token_provider import OpenProjectTokenProvider


class ContextMiddleware(BaseHTTPMiddleware):
    """Starlette middleware to seed and reset ContextVars per request."""

    async def dispatch(self, request: Request, call_next: Callable):
        # Allow link/unlink to bypass token resolution
        if request.url.path in {"/link/openproject", "/unlink/openproject"}:
            return await call_next(request)

        # Read env directly – never fails, just returns empty strings.
        env_base_url, env_api_key = load_env_config(use_dotenv=False)

        api_key = extract_api_key(
            request.headers,
            fallback=env_api_key or None,
        )

        request_id = getattr(request.state, "request_id", None) or request.headers.get(
            REQUEST_ID_HEADER
        )
        user_agent = request.headers.get("User-Agent")

        ctx_request_id = (
            request.state.request_id if hasattr(request.state, "request_id") else None
        )
        if not ctx_request_id:
            ctx_request_id = request.headers.get(REQUEST_ID_HEADER) or ""

        tokens = None
        try:
            # Resolve token: prefer linked token for principal, else header/env
            principal = getattr(request.state, "auth_principal", None)
            store = getattr(request.app.state, "token_store", None)
            if store is None:
                # Fallback for legacy setups/tests that don't inject a store
                from openproject_mcp.transports.http.token_store import MemoryTokenStore

                store = MemoryTokenStore(enc_key=None)
                request.app.state.token_store = store

            provider = OpenProjectTokenProvider(
                store=store,
                env_api_key=env_api_key or None,
                env_base_url=env_base_url or None,
            )
            resolved_api_key, resolved_base_url = provider.resolve(
                principal, api_key or None
            )
            tokens = list(
                apply_request_context(
                    api_key=resolved_api_key or "",
                    base_url=resolved_base_url or "",
                    request_id=request_id,
                    user_agent=user_agent,
                    auth_principal=principal,
                    auth_scopes=getattr(request.state, "oauth_scopes", ()),
                )
            )
            context = get_context(require_api_key=True, require_base_url=True)
            response: Response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = context.request_id
            return response
        except MissingBaseUrlError as exc:
            return self._error_response(
                status=500,
                code="missing_base_url",
                message=str(exc),
                request_id=ctx_request_id
                or request.headers.get(REQUEST_ID_HEADER)
                or "",
            )
        except MissingApiKeyError as exc:
            return self._error_response(
                status=401,
                code="missing_api_key",
                message=str(exc),
                request_id=ctx_request_id
                or request.headers.get(REQUEST_ID_HEADER)
                or "",
            )
        except TokenNotLinkedError as exc:
            return self._error_response(
                status=401,
                code="missing_api_key",
                message=str(exc),
                request_id=ctx_request_id
                or request.headers.get(REQUEST_ID_HEADER)
                or "",
            )
        finally:
            if tokens is not None:
                reset_context(tokens)

    @staticmethod
    def _error_response(
        *, status: int, code: str, message: str, request_id: str
    ) -> Response:
        body = {
            "error": code,
            "message": message,
            "request_id": request_id,
        }
        response = Response(
            json.dumps(body),
            status_code=status,
            media_type="application/json",
            headers={REQUEST_ID_HEADER: request_id},
        )
        return response


__all__ = ["ContextMiddleware"]
