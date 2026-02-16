"""Compatibility shim: stdio runner entrypoint."""

from openproject_mcp.core.config import create_client_from_env
from openproject_mcp.transports.stdio.main import main

__all__ = ["create_client_from_env", "main"]
