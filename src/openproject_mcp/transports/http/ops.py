from __future__ import annotations

from typing import Dict

OPS_PATHS = {"/healthz", "/readyz"}


def is_ops_path(path: str | None) -> bool:
    return bool(path) and path in OPS_PATHS


def build_readiness_status(readiness_state: Dict[str, bool]) -> Dict[str, object]:
    failed = [k for k, v in readiness_state.items() if not v]
    status = "ok" if not failed else "fail"
    return {
        "status": status,
        "checks": readiness_state,
        "failed": failed,
    }


__all__ = ["is_ops_path", "build_readiness_status", "OPS_PATHS"]
