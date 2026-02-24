from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from openproject_mcp.transports.http.token_crypto import decrypt_token, encrypt_token

# Per-process random salt so principal digests are not rainbow-table-reversible.
# Survives for the lifetime of the process; after restart a new salt is drawn
# and all in-memory store entries are lost anyway.
_PRINCIPAL_HMAC_KEY: bytes = os.urandom(32)

Principal = Tuple[str, str]


@dataclass
class StoredToken:
    api_token: str
    base_url: Optional[str]
    created_at: float
    updated_at: float
    status: str = "active"


class TokenStore:
    def get(
        self, principal: Principal
    ) -> Optional[StoredToken]:  # pragma: no cover - interface
        raise NotImplementedError

    def set(
        self, principal: Principal, api_token: str, base_url: Optional[str]
    ) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def delete(self, principal: Principal) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class MemoryTokenStore(TokenStore):
    def __init__(self, enc_key: str | None = None):
        self._data: Dict[Principal, StoredToken] = {}
        self._enc_key = enc_key

    def _maybe_encrypt(self, token: str) -> str:
        if not self._enc_key:
            return token
        return encrypt_token(token, self._enc_key)

    def _maybe_decrypt(self, token: str) -> str:
        if not self._enc_key:
            return token
        return decrypt_token(token, self._enc_key)

    def get(self, principal: Principal) -> Optional[StoredToken]:
        stored = self._data.get(principal)
        if not stored:
            return None
        return StoredToken(
            api_token=self._maybe_decrypt(stored.api_token),
            base_url=stored.base_url,
            created_at=stored.created_at,
            updated_at=stored.updated_at,
            status=stored.status,
        )

    def set(
        self, principal: Principal, api_token: str, base_url: Optional[str]
    ) -> None:
        now = time.time()
        prev = self._data.get(principal)
        created = prev.created_at if prev else now
        self._data[principal] = StoredToken(
            api_token=self._maybe_encrypt(api_token),
            base_url=base_url,
            created_at=created,
            updated_at=now,
            status="active",
        )

    def delete(self, principal: Principal) -> None:
        self._data.pop(principal, None)


def principal_from_api_key(api_key: str) -> Principal:
    """Derive a principal tuple from a raw API key.

    Uses HMAC-SHA256 with a per-process random secret so the digest
    is not reversible via rainbow tables even if exposed.
    """
    digest = hmac.new(
        _PRINCIPAL_HMAC_KEY, api_key.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return ("api-key", digest)


__all__ = [
    "TokenStore",
    "MemoryTokenStore",
    "StoredToken",
    "Principal",
    "principal_from_api_key",
]
