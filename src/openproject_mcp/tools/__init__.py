"""
Tool namespace for OpenProject MCP.

Individual tool modules (e.g., metadata, projects) should be imported here
when they need to be exposed for discovery/registration.
"""

# Keeping this file explicit to ensure the package is importable during tests.

# Tool modules
from .attachments import attach_file_to_wp, list_attachments
from .memberships import get_project_memberships
from .metadata import (
    AmbiguousResolutionError,
    NotFoundResolutionError,
    ResolutionError,
    list_priorities,
    list_statuses,
    list_types,
    resolve_metadata_id,
    resolve_priority_id,
    resolve_project,
    resolve_status,
    resolve_status_id,
    resolve_type,
    resolve_type_for_project,
    resolve_type_id,
    resolve_user,
)
from .projects import list_projects
from .system import system_ping
from .time_entries import log_time
from .work_packages import (
    add_comment,
    append_work_package_description,
    create_work_package,
    get_work_package,
    get_work_package_statuses,
    get_work_package_types,
    list_work_packages,
    search_content,
    update_status,
)

__all__ = [
    "list_types",
    "list_statuses",
    "list_priorities",
    "ResolutionError",
    "AmbiguousResolutionError",
    "NotFoundResolutionError",
    "resolve_metadata_id",
    "resolve_type_id",
    "resolve_status_id",
    "resolve_priority_id",
    "resolve_type",
    "resolve_status",
    "resolve_type_for_project",
    "resolve_project",
    "resolve_user",
    "list_projects",
    "attach_file_to_wp",
    "list_attachments",
    "get_project_memberships",
    "system_ping",
    "add_comment",
    "list_work_packages",
    "get_work_package",
    "append_work_package_description",
    "search_content",
    "get_work_package_statuses",
    "get_work_package_types",
    "create_work_package",
    "update_status",
    "log_time",
]
