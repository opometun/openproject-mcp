import pytest

from openproject_mcp.core.context import apply_request_context, reset_context
from openproject_mcp.core.registry import _wrap_tool


@pytest.mark.asyncio
async def test_wrapped_tool_ignores_stale_required_scopes_attribute():
    async def tool(client):
        return "ok"

    tool.__required_scopes__ = ("wp:write",)
    wrapped = _wrap_tool(tool, lambda: None)

    tokens = apply_request_context(
        api_key="k",
        base_url="http://example.com",
        request_id="rid",
    )
    try:
        assert await wrapped() == "ok"
    finally:
        reset_context(tokens)


def test_write_tools_have_no_local_scope_annotations():
    from openproject_mcp.core.tools import attachments, time_entries, work_packages

    write_tools = [
        work_packages.create_work_package,
        work_packages.update_status,
        work_packages.update_work_package,
        work_packages.add_comment,
        work_packages.append_work_package_description,
        time_entries.log_time,
        attachments.attach_file_to_wp,
    ]

    for func in write_tools:
        assert not hasattr(func, "__required_scopes__")
