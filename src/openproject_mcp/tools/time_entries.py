from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from openproject_mcp.client import OpenProjectClient
from openproject_mcp.utils.time_parser import DurationParseError, parse_duration_string


async def log_time(
    client: OpenProjectClient,
    work_package_id: int,
    duration: str,
    comment: str = "",
    activity_id: int = 1,
    spent_on: Optional[date] = None,
) -> str:
    """
    Log time on a work package.

    Args:
        work_package_id: Target work package ID.
        duration: Human string like "2h", "30m", "2h 30m".
        comment: Optional comment.
        activity_id: Activity to assign; Stage 1 assumes caller provides a valid ID.
        spent_on: Date; defaults to today.

    Returns:
        Success message with work package id and original duration string.
    """
    try:
        iso_duration = parse_duration_string(duration)
    except DurationParseError as exc:
        return (
            f"Error: {exc} Accepted examples: '2h', '30m', '2h 30m'. "
            "Use hours (h) and minutes (m)."
        )

    spent_on_value = (spent_on or date.today()).isoformat()

    payload: Dict[str, Any] = {
        "hours": iso_duration,
        "comment": {"raw": comment},
        "spentOn": spent_on_value,
        "_links": {
            "entity": {"href": f"/api/v3/work_packages/{work_package_id}"},
            "activity": {"href": f"/api/v3/time_entries/activities/{activity_id}"},
        },
    }

    await client.post("/api/v3/time_entries", json=payload, tool="time_entries")
    return f"Logged {duration} to work package {work_package_id} on {spent_on_value}."
