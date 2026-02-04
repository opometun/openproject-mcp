from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

# Pattern captures compact or spaced tokens, e.g., "2h30m", "2h 30m", "1.5h"
HOURS_RE = re.compile(r"(\d+(?:\.\d+)?)h")
MINUTES_RE = re.compile(r"(\d+(?:\.\d+)?)m")


class DurationParseError(ValueError):
    """Raised when a duration string cannot be parsed into ISO 8601 format."""


def parse_duration_string(duration_str: str) -> str:
    """
    Parse human-friendly durations like "2h", "30m", "2h 30m", "1.5h" into ISO 8601.

    Rules:
    - Accept hours/minutes tokens (h/m), compact or spaced.
    - Decimals allowed (e.g., 1.5h -> 1h30m); rounding is HALF_UP to the nearest minute.
    - Reject negatives or inputs with no valid tokens.
    """
    if duration_str is None:
        raise DurationParseError("Duration is required.")

    normalized = " ".join(duration_str.lower().strip().split())
    if not normalized:
        raise DurationParseError("Duration is required.")
    if "-" in normalized:
        raise DurationParseError("Negative durations are not allowed.")

    hours = _sum_matches(HOURS_RE, normalized)
    minutes = _sum_matches(MINUTES_RE, normalized)

    total_minutes = (hours * 60) + minutes
    # Round to nearest whole minute, half up
    total_minutes = total_minutes.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    if total_minutes <= 0:
        raise DurationParseError(
            "Duration must be greater than zero (e.g., '2h', '30m')."
        )

    total_minutes_int = int(total_minutes)
    h = total_minutes_int // 60
    m = total_minutes_int % 60

    parts = ["PT"]
    if h:
        parts.append(f"{h}H")
    if m:
        parts.append(f"{m}M")
    if len(parts) == 1:  # neither hours nor minutes
        raise DurationParseError(
            "Duration must include hours or minutes (e.g., '2h', '30m')."
        )

    return "".join(parts)


def _sum_matches(pattern: re.Pattern[str], text: str) -> Decimal:
    total = Decimal("0")
    for match in pattern.finditer(text):
        total += Decimal(match.group(1))
    return total
