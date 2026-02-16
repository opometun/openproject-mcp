from __future__ import annotations

import os
from typing import Tuple

from . import client as _client
from .client import OpenProjectClient


def load_env_config(*, use_dotenv: bool = True) -> Tuple[str, str]:
    """Load OpenProject base URL and API key from environment (optional .env)."""
    if use_dotenv:
        _client.load_dotenv()
    base_url = os.getenv("OPENPROJECT_BASE_URL", "").strip()
    api_key = os.getenv("OPENPROJECT_API_KEY", "").strip()
    return base_url, api_key


def create_client_from_env(**kwargs) -> OpenProjectClient:
    """Create an OpenProjectClient from environment variables."""
    base_url, api_key = load_env_config()
    if not base_url or not api_key:
        raise ValueError(
            "Missing OPENPROJECT_BASE_URL or OPENPROJECT_API_KEY in environment."
        )
    return OpenProjectClient(base_url=base_url, api_key=api_key, **kwargs)


__all__ = ["load_env_config", "create_client_from_env"]
