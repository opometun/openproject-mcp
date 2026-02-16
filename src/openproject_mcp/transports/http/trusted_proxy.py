from __future__ import annotations

from ipaddress import ip_address, ip_network
from typing import Iterable

from starlette.requests import Request

from openproject_mcp.transports.http.config import HttpConfig


def _client_ip(request: Request) -> str | None:
    # Starlette places client in scope under "client": (host, port)
    client = request.client
    return client.host if client else None


def _ip_in_trusted(ip: str, trusted_cidrs: Iterable[str]) -> bool:
    candidate = ip_address(ip)
    for cidr in trusted_cidrs:
        if candidate in ip_network(cidr, strict=False):
            return True
    return False


def is_https_request(request: Request, cfg: HttpConfig) -> bool:
    # Direct HTTPS
    if request.url.scheme.lower() == "https":
        return True

    if not cfg.trust_proxy_headers:
        return False

    client_ip = _client_ip(request)
    if not client_ip or not _ip_in_trusted(client_ip, cfg.trusted_proxies):
        return False

    forwarded = request.headers.get("forwarded")
    if forwarded:
        # Simple parse: look for proto=https in first entry
        parts = forwarded.split(";")
        for part in parts:
            if part.strip().lower() == "proto=https":
                return True

    xf_proto = request.headers.get("x-forwarded-proto")
    if xf_proto and xf_proto.split(",")[0].strip().lower() == "https":
        return True

    return False


__all__ = ["is_https_request"]
