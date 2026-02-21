from __future__ import annotations

import logging
from typing import Any, Dict

RESERVED_LOG_KEYS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
}


def _clean_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in fields.items() if k not in RESERVED_LOG_KEYS}


def log_event(event: str, logger: logging.Logger | None = None, **fields: Any) -> None:
    """
    Minimal structured logging helper.
    - Uses logger.info with extra dict so formatters can include keys.
    - Drops reserved LogRecord attributes to avoid collisions.
    """
    log = logger or logging.getLogger("openproject_mcp.observability")
    extra = {"event": event, **_clean_fields(fields)}
    log.info(event, extra=extra)


__all__ = ["log_event"]
