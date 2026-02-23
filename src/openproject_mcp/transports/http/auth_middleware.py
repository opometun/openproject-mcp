from __future__ import annotations

import json
import time
from typing import Callable, Dict, Tuple

import httpx
import jwt
from jwt import InvalidTokenError
from jwt.algorithms import RSAAlgorithm
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from openproject_mcp.transports.http.config import HttpConfig


def _looks_like_jwt(token: str) -> bool:
    return token.count(".") == 2


class _JWKCache:
    def __init__(self, url: str, ttl: int):
        self.url = url
        self.ttl = ttl
        self._cached: Tuple[float, Dict[str, object]] | None = None
        self._client = httpx.AsyncClient()

    async def get(self) -> Dict[str, object]:
        now = time.time()
        if self._cached and now - self._cached[0] < self.ttl:
            return self._cached[1]
        resp = await self._client.get(self.url, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        self._cached = (now, data)
        return data


async def _jwt_claims(
    token: str, cfg: HttpConfig, jwk_cache: _JWKCache
) -> Dict[str, object]:
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    jwks = await jwk_cache.get()
    keys = jwks.get("keys", []) if isinstance(jwks, dict) else []
    key = next((k for k in keys if k.get("kid") == kid), None)
    if key is None:
        raise InvalidTokenError("Signing key not found in JWKS")
    public_key = RSAAlgorithm.from_jwk(json.dumps(key))
    alg = key.get("alg") or "RS256"
    return jwt.decode(
        token,
        public_key,
        algorithms=[alg],
        audience=cfg.oauth_audience,
        issuer=cfg.oauth_issuer,
    )


class AuthMiddleware(BaseHTTPMiddleware):
    """Dual auth: OAuth JWT (Google) OR API key. No breaking change for API keys."""

    def __init__(self, app, cfg: HttpConfig):
        super().__init__(app)
        self.cfg = cfg
        self._jwk_cache = _JWKCache(cfg.oauth_jwks_url, cfg.oauth_jwks_cache_ttl)

    async def dispatch(self, request: Request, call_next: Callable):
        # Allow discovery without auth
        if (
            self.cfg.oauth_enabled
            and request.url.path == "/.well-known/oauth-protected-resource"
        ):
            return await call_next(request)

        headers = request.headers
        bearer = self._extract_bearer(headers)
        looks_jwt = _looks_like_jwt(bearer) if bearer else False

        # 1) Bearer present
        if bearer:
            if looks_jwt and self.cfg.oauth_enabled:
                try:
                    claims = await _jwt_claims(bearer, self.cfg, self._jwk_cache)
                    request.state.auth_principal = (
                        claims.get("iss"),
                        claims.get("sub"),
                    )
                    request.state.oauth_claims = claims
                    return await call_next(request)
                except Exception:
                    return self._unauthorized(request, bearer_challenge=True)
            # OAuth disabled OR non-JWT → treat as API key and fall through
            if bearer:
                # Mark for downstream context extraction; ContextMiddleware will read headers again  # noqa: E501
                return await call_next(request)

        # 2) API key headers
        if (
            headers.get("X-OpenProject-Key")
            or headers.get("x-openproject-key")
            or headers.get("X-API-Key")
        ):
            return await call_next(request)

        # 3) No auth provided
        if self.cfg.oauth_enabled:
            return self._unauthorized(request, bearer_challenge=True)
        # OAuth disabled: defer to existing ContextMiddleware to produce legacy errors
        return await call_next(request)

    @staticmethod
    def _extract_bearer(headers: Dict[str, str]) -> str | None:
        auth = headers.get("authorization") or headers.get("Authorization")
        if not auth:
            return None
        if not auth.lower().startswith("bearer "):
            return None
        token = auth.split(" ", 1)[1].strip()
        return token or None

    def _unauthorized(self, request: Request, bearer_challenge: bool) -> Response:
        rid = getattr(request.state, "request_id", "") or ""
        headers = {"Cache-Control": "no-store"}
        if rid:
            headers["X-Request-Id"] = rid
        if bearer_challenge and self.cfg.oauth_enabled:
            # Provide discovery link for ChatGPT
            host = request.headers.get("host") or request.url.netloc
            resource = f"{request.url.scheme}://{host}"
            well_known = f"{resource}/.well-known/oauth-protected-resource"
            headers["WWW-Authenticate"] = (
                f'Bearer authorization_uri="{well_known}", resource="{resource}"'
            )
        body = {
            "error": "unauthorized",
            "message": "Authentication required",
            "request_id": rid,
        }
        return JSONResponse(body, status_code=401, headers=headers)


__all__ = ["AuthMiddleware"]
