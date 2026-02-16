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
    seed_from_headers,
)


class ContextMiddleware(BaseHTTPMiddleware):
    """Starlette middleware to seed and reset ContextVars per request."""

    async def dispatch(self, request: Request, call_next: Callable):
        ctx_candidate = seed_from_headers(request.headers)
        tokens = []
        try:
            tokens = list(
                apply_request_context(
                    api_key=ctx_candidate.api_key,
                    base_url=ctx_candidate.base_url,
                    request_id=ctx_candidate.request_id,
                    user_agent=ctx_candidate.user_agent,
                )
            )
            context = get_context(require_api_key=True, require_base_url=True)
            response: Response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = context.request_id
            return response
        except MissingApiKeyError as exc:
            return self._error_response(
                status=401, code="missing_api_key", message=str(exc), ctx=ctx_candidate
            )
        except MissingBaseUrlError as exc:
            return self._error_response(
                status=500, code="missing_base_url", message=str(exc), ctx=ctx_candidate
            )
        finally:
            reset_context(tokens)

    @staticmethod
    def _error_response(*, status: int, code: str, message: str, ctx) -> Response:
        body = {
            "error": code,
            "message": message,
            "request_id": ctx.request_id,
        }
        response = Response(
            json.dumps(body),
            status_code=status,
            media_type="application/json",
            headers={REQUEST_ID_HEADER: ctx.request_id},
        )
        return response


__all__ = ["ContextMiddleware"]
