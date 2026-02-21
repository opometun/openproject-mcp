import logging
from typing import Any

LOG_EXTRA_FIELDS = (
    "request_id",
    "method",
    "path",
    "endpoint",
    "status",
    "duration_ms",
    "tool",
    "attempt",
)


class LogfmtFormatter(logging.Formatter):
    """Small logfmt-style formatter that tolerates missing extras."""

    def format(self, record: logging.LogRecord) -> str:  # pragma: no cover - trivial
        kv: list[str] = [
            f"level={record.levelname.lower()}",
            f"logger={record.name}",
        ]

        msg = record.getMessage()
        if msg:
            kv.append(f"event={self._fmt_val(msg)}")

        for key in LOG_EXTRA_FIELDS:
            val = getattr(record, key, None)
            if val is None:
                continue
            kv.append(f"{key}={self._fmt_val(val)}")

        if record.exc_info:
            kv.append(f"exc_type={record.exc_info[0].__name__}")

        return " ".join(kv)

    @staticmethod
    def _fmt_val(val: Any) -> str:
        if isinstance(val, (int, float, bool)):
            return str(val)
        s = str(val)
        if " " in s or "=" in s:
            s = '"' + s.replace('"', '\\"') + '"'
        return s


def setup_logging(level: str = "INFO") -> None:
    """Initialize root logging with logfmt output including request context."""

    root = logging.getLogger()
    # Avoid duplicate handlers if called twice
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler()
    handler.setFormatter(LogfmtFormatter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


__all__ = ["setup_logging", "LogfmtFormatter", "LOG_EXTRA_FIELDS"]
