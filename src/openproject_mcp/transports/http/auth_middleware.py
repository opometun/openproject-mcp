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
from openproject_mcp.transports.http.token_store import principal_from_api_key


def _looks_like_jwt(token: str) -> bool:
    return token.count(".") == 2


class _JWKCache:
    def __init__(self, url: str, ttl: int):
        self.url = url
        self.ttl = ttl
        self._cached: Tuple[float, Dict[str, object]] | None = None

    async def get(self) -> Dict[str, object]:
        now = time.time()
        if self._cached and now - self._cached[0] < self.ttl:
            return self._cached[1]
        async with httpx.AsyncClient() as client:
            resp = await client.get(self.url, timeout=5.0)
            resp.raise_for_status()
            data = resp.json()
        self._cached = (now, data)
        return data


async def _jwt_claims(
    token: str, cfg: HttpConfig, jwk_cache: _JWKCache, audience: str | None
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
        audience=audience,
        issuer=None if len(cfg.oauth_issuer) > 1 else cfg.oauth_issuer[0],
    )


class AuthMiddleware(BaseHTTPMiddleware):
    """Dual auth: OAuth JWT (Google) OR API key. Set auth_principal for link lookups."""

    def __init__(self, app, cfg: HttpConfig):
        super().__init__(app)
        self.cfg = cfg
        self._jwk_caches = {
            issuer: _JWKCache(url, cfg.oauth_jwks_cache_ttl)
            for issuer, url in zip(cfg.oauth_issuer, cfg.oauth_jwks_url, strict=False)
        }

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
                    claims = await self._validate_jwt(bearer)
                    request.state.auth_principal = (
                        claims.get("iss"),
                        claims.get("sub"),
                    )
                    request.state.oauth_claims = claims
                    scopes_val = claims.get("scope") or claims.get("scopes") or ""
                    request.state.oauth_scopes = tuple(
                        s for s in scopes_val.split() if s.strip()
                    )
                    return await call_next(request)
                except Exception:
                    return self._unauthorized(request, bearer_challenge=True)
            # OAuth disabled OR non-JWT → treat as API key and fall through
            if bearer:
                request.state.auth_principal = principal_from_api_key(bearer)
                return await call_next(request)

        # 2) API key headers
        if (
            headers.get("X-OpenProject-Key")
            or headers.get("x-openproject-key")
            or headers.get("X-API-Key")
        ):
            key = (
                headers.get("X-OpenProject-Key")
                or headers.get("x-openproject-key")
                or headers.get("X-API-Key")
            )
            if key:
                request.state.auth_principal = principal_from_api_key(key)
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

    async def _validate_jwt(self, token: str) -> Dict[str, object]:
        # Try each issuer; audience can be single (applied to all) or per-issuer
        for idx, issuer in enumerate(self.cfg.oauth_issuer):
            jwk_cache = self._jwk_caches[issuer]
            audience = (
                self.cfg.oauth_audience[idx]
                if self.cfg.oauth_audience and len(self.cfg.oauth_audience) > 1
                else (self.cfg.oauth_audience[0] if self.cfg.oauth_audience else None)
            )
            try:
                claims = await _jwt_claims(token, self.cfg, jwk_cache, audience)
                if claims.get("iss") == issuer:
                    # Scope check if required
                    if self.cfg.oauth_required_scopes:
                        token_scopes = set(
                            (claims.get("scope") or claims.get("scopes") or "").split()
                        )
                        required = set(self.cfg.oauth_required_scopes)
                        if not required.issubset(token_scopes):
                            raise InvalidTokenError("missing required scopes")
                    return claims
            except InvalidTokenError:
                continue
        raise InvalidTokenError("No matching issuer/audience for token")

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
