"""
Tool namespace for OpenProject MCP.

Individual tool modules (e.g., metadata, projects) should be imported here
when they need to be exposed for discovery/registration.
"""

# Keeping this file explicit to ensure the package is importable during tests.

# Tool modules
from .attachments import (
    attach_file_to_wp,
    download_attachment,
    get_attachment_content,
    list_attachments,
)
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
from .queries import list_queries, run_query
from .system import system_ping
from .time_entries import get_my_logged_time, list_time_entries, log_time
from .users import get_user_by_id
from .work_packages import (
    add_comment,
    append_work_package_description,
    create_work_package,
    get_work_package,
    get_work_package_statuses,
    get_work_package_types,
    list_work_package_versions,
    list_work_packages,
    search_content,
    update_status,
    update_work_package,
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
    "list_queries",
    "run_query",
    "attach_file_to_wp",
    "list_attachments",
    "download_attachment",
    "get_attachment_content",
    "get_project_memberships",
    "system_ping",
    "add_comment",
    "list_work_packages",
    "get_work_package",
    "append_work_package_description",
    "search_content",
    "get_work_package_statuses",
    "get_work_package_types",
    "list_work_package_versions",
    "create_work_package",
    "update_status",
    "update_work_package",
    "log_time",
    "list_time_entries",
    "get_my_logged_time",
    "get_user_by_id",
]
