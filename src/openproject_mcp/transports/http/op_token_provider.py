from __future__ import annotations

from typing import Optional

from openproject_mcp.transports.http.errors import TokenNotLinkedError
from openproject_mcp.transports.http.token_store import TokenStore


class OpenProjectTokenProvider:
    """Resolve OP API token for the current request principal."""

    def __init__(
        self, store: TokenStore, env_api_key: Optional[str], env_base_url: Optional[str]
    ):
        self.store = store
        self.env_api_key = env_api_key
        self.env_base_url = env_base_url

    def resolve(
        self, principal, fallback_api_key: Optional[str]
    ) -> tuple[str, Optional[str]]:
        """Return (api_key, base_url) for the principal.

        Precedence:
        1) token store entry for principal
        2) fallback_api_key (header/env) with env_base_url
        Raises ValueError if no token available.
        """
        record = self.store.get(principal) if principal else None
        if record and record.status == "active":
            return record.api_token, record.base_url or self.env_base_url
        if fallback_api_key:
            return fallback_api_key, self.env_base_url
        raise TokenNotLinkedError("API token not linked for this principal")


__all__ = ["OpenProjectTokenProvider"]
