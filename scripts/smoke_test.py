from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from typing import Optional

from openproject_mcp.client import OpenProjectClient, OpenProjectHTTPError
from openproject_mcp.models import WorkPackageCreateInput, WorkPackageUpdateStatusInput
from openproject_mcp.tools.metadata import list_statuses, list_types
from openproject_mcp.tools.projects import list_projects
from openproject_mcp.tools.work_packages import (
    create_work_package,
    get_work_package,
    update_status,
)


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    val = os.getenv(name)
    return val if val else default


def _print_step(title: str) -> None:
    print(f"\n== {title}")


def _fail(msg: str) -> int:
    print(f"FAILED: {msg}")
    return 1


async def run_smoke_test() -> int:
    # --- Config ---
    base_url = os.getenv("OPENPROJECT_BASE_URL")
    api_key = os.getenv("OPENPROJECT_API_KEY")
    if not base_url or not api_key:
        return _fail("Missing OPENPROJECT_BASE_URL or OPENPROJECT_API_KEY.")

    cfg_project_id = _env("TEST_PROJECT_ID")
    cfg_project_identifier = _env("TEST_PROJECT_IDENTIFIER")
    cfg_type = _env("TEST_WP_TYPE")
    cfg_status = _env("TEST_TARGET_STATUS")
    cleanup = _env("SMOKE_TEST_CLEANUP", "0") == "1"

    print("Config:")
    print(f"  base_url: {base_url}")
    print(f"  project_id: {cfg_project_id}")
    print(f"  project_identifier: {cfg_project_identifier}")
    print(f"  type: {cfg_type}")
    print(f"  target_status: {cfg_status}")
    print(f"  cleanup: {cleanup}")

    client = OpenProjectClient(base_url=base_url, api_key=api_key)

    # --- List projects ---
    _print_step("List projects")
    async with client:
        projects_payload = await list_projects(client)
        projects = projects_payload.get("items", [])
        if not projects:
            return _fail("No projects available.")

        selected = None
        if cfg_project_id:
            try:
                pid = int(cfg_project_id)
                selected = next((p for p in projects if p.get("id") == pid), None)
            except ValueError:
                return _fail("TEST_PROJECT_ID must be an integer.")
        if not selected and cfg_project_identifier:
            # list_projects output lacks identifier; try name match instead
            selected = next(
                (
                    p
                    for p in projects
                    if str(p.get("name", "")).lower() == cfg_project_identifier.lower()
                ),
                None,
            )
        if not selected:
            selected = projects[0]

        project_name = selected.get("name")
        project_id = selected.get("id")
        if project_id is None:
            return _fail("Selected project has no id.")

        print(f"Selected project: {project_name} (id={project_id})")

        # --- Resolve type ---
        _print_step("Resolve type")
        types = await list_types(client)
        if not types:
            return _fail("No types available.")

        type_choice = None
        if cfg_type:
            type_choice = next(
                (t for t in types if t["name"].lower() == cfg_type.lower()), None
            )
        if not type_choice:
            for candidate in ("Bug", "Task"):
                type_choice = next(
                    (t for t in types if t["name"].lower() == candidate.lower()), None
                )
                if type_choice:
                    break
        if not type_choice:
            type_choice = types[0]

        type_name = type_choice["name"]
        print(f"Type: {type_name} (id={type_choice['id']})")

        # --- Resolve status ---
        _print_step("Resolve status")
        statuses = await list_statuses(client)
        if not statuses:
            return _fail("No statuses available.")

        status_choice = None
        if cfg_status:
            status_choice = next(
                (s for s in statuses if s["name"].lower() == cfg_status.lower()), None
            )
        if not status_choice:
            status_choice = next(
                (s for s in statuses if s["name"].lower() == "in progress"), None
            )
        if not status_choice:
            status_choice = next((s for s in statuses if not s.get("is_closed")), None)
        if not status_choice:
            status_choice = statuses[0]

        status_name = status_choice["name"]
        print(f"Target status: {status_name} (id={status_choice['id']})")

        # --- Create work package ---
        _print_step("Create work package")
        subject = f"Smoke Test {datetime.utcnow().isoformat(timespec='seconds')}Z"
        wp_input = WorkPackageCreateInput(
            project=str(project_name),  # tools resolve by name/identifier
            type=type_name,
            subject=subject,
            description="Automated smoke test artifact.",
        )
        try:
            created = await create_work_package(client, data=wp_input)
        except OpenProjectHTTPError as exc:
            return _fail(f"Create failed: {exc}")

        wp_id = created.get("id")
        if wp_id is None:
            return _fail("Create did not return an id.")
        print(f"Created WP id={wp_id}, subject='{subject}'")

        # --- Update status ---
        _print_step("Update status")
        try:
            await update_status(
                client,
                data=WorkPackageUpdateStatusInput(id=wp_id, status=status_name),
            )
        except OpenProjectHTTPError as exc:
            return _fail(f"Update status failed: {exc}")
        print(f"Updated status to '{status_name}'")

        # --- Verify ---
        _print_step("Verify")
        wp = await get_work_package(client, wp_id)
        returned_status = (
            wp.get("status", {}).get("name")
            if isinstance(wp.get("status"), dict)
            else None
        )

        if returned_status and returned_status.lower() != status_name.lower():
            return _fail(
                f"Verification failed: expected status '{status_name}', "
                f"got '{returned_status}'"
            )
        print("Verification OK")

        # --- Cleanup (optional) ---
        _print_step("Cleanup")
        if cleanup:
            print(
                "Cleanup requested: no delete API implemented; "
                "leaving work package in place."
            )
        else:
            print(
                "Cleanup skipped (SMOKE_TEST_CLEANUP=0). Work package left in system."
            )

    print("\nPASSED smoke test.")
    return 0


def main() -> None:
    exit_code = asyncio.run(run_smoke_test())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
