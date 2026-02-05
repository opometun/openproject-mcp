"""
Tool namespace for OpenProject MCP.

Individual tool modules (e.g., metadata, projects) should be imported here
when they need to be exposed for discovery/registration.
"""

# Keeping this file explicit to ensure the package is importable during tests.

# Tool modules
from .metadata import (
    list_priorities,
    list_statuses,
    list_types,
    resolve_metadata_id,
    resolve_priority_id,
    resolve_status_id,
    resolve_type_id,
)
from .projects import list_projects
from .system import system_ping
from .time_entries import log_time
from .work_packages import (
    create_work_package,
    get_work_package,
    list_work_packages,
    update_status,
)

__all__ = [
    "list_types",
    "list_statuses",
    "list_priorities",
    "resolve_metadata_id",
    "resolve_type_id",
    "resolve_status_id",
    "resolve_priority_id",
    "list_projects",
    "system_ping",
    "list_work_packages",
    "get_work_package",
    "create_work_package",
    "update_status",
    "log_time",
]
