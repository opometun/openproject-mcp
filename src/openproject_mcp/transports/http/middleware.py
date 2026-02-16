from __future__ import annotations

import json
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from openproject_mcp.core.context import (
    REQUEST_ID_HEADER,
    MissingApiKeyError,
    MissingBaseUrlError,
    apply_request_context,
    get_context,
    reset_context,
    seed_from_env,
)


class ContextMiddleware(BaseHTTPMiddleware):
    """Starlette middleware to seed and reset ContextVars per request."""

    async def dispatch(self, request: Request, call_next: Callable):
        # Seed from env defaults (no dotenv for HTTP)
        try:
            env_ctx = seed_from_env(use_dotenv=False)
        except Exception:
            env_ctx = None

        api_key = request.headers.get("X-OpenProject-Key") or (
            env_ctx.api_key if env_ctx else None
        )
        base_url = env_ctx.base_url if env_ctx else None
        request_id = request.headers.get(REQUEST_ID_HEADER)
        user_agent = request.headers.get("User-Agent")

        tokens = []
        ctx_request_id = request_id
        if not ctx_request_id:
            # ensure we have an ID even for early errors
            ctx_request_id = request.headers.get(REQUEST_ID_HEADER) or ""

        tokens = []
        try:
            tokens = list(
                apply_request_context(
                    api_key=api_key or "",
                    base_url=base_url or "",
                    request_id=request_id,
                    user_agent=user_agent,
                )
            )
            context = get_context(require_api_key=True, require_base_url=True)
            response: Response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = context.request_id
            return response
        except MissingApiKeyError as exc:
            return self._error_response(
                status=401,
                code="missing_api_key",
                message=str(exc),
                request_id=ctx_request_id
                or request.headers.get(REQUEST_ID_HEADER)
                or "",
            )
        except MissingBaseUrlError as exc:
            return self._error_response(
                status=500,
                code="missing_base_url",
                message=str(exc),
                request_id=ctx_request_id
                or request.headers.get(REQUEST_ID_HEADER)
                or "",
            )
        finally:
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
