import json
from pathlib import Path

from openproject_mcp.models import Project, Status, User, WorkPackage


def load_fixture(name: str) -> dict:
    p = Path(__file__).parent / "fixtures" / name
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def test_project_parses_and_summary():
    payload = load_fixture("project_list.json")
    # Handle the fact that our fixture is a Collection
    first = payload["_embedded"]["elements"][0]

    project = Project.model_validate(first)
    summary = project.to_summary()

    assert isinstance(summary.id, int)
    assert isinstance(summary.name, str)
    assert isinstance(summary.identifier, str)
    assert isinstance(summary.active, bool)

    # Verify description helper
    assert isinstance(project.description_text, str)


def test_user_parses_and_summary():
    """Test User model parsing and summary conversion."""
    user_data = {
        "_type": "User",
        "id": 1,
        "name": "OpenProject Admin",
        "login": "admin",
        "admin": True,
        "_links": {"self": {"href": "/api/v3/users/1"}},
    }

    user = User.model_validate(user_data)
    summary = user.to_summary()

    assert summary.id == 1
    assert summary.name == "OpenProject Admin"
    assert summary.login == "admin"


def test_status_parses_and_summary():
    """Test Status model parsing and summary conversion."""
    status_data = {
        "_type": "Status",
        "id": 1,
        "name": "New",
        "isClosed": False,
        "color": "#1A67A3",
        "_links": {"self": {"href": "/api/v3/statuses/1"}},
    }

    status = Status.model_validate(status_data)
    summary = status.to_summary()

    assert summary.id == 1
    assert summary.name == "New"
    assert summary.is_closed is False
    assert status.color == "#1A67A3"


def test_work_package_link_titles_and_ids():
    wp_payload = load_fixture("work_package.json")

    # If the fixture is a collection/list, extract the first item
    if wp_payload.get("_type") in ("Collection", "WorkPackageCollection"):
        wp_payload = wp_payload["_embedded"]["elements"][0]

    wp = WorkPackage.model_validate(wp_payload)

    # Alias check
    assert isinstance(wp.lock_version, int)

    # Link titles (verifies HAL logic)
    # Note: If your sanitized data replaced these with strings, this passes.
    # If keys are missing, these might return "Unknown" or "Normal".
    assert wp.status_title != "Unknown"

    # Link IDs (verifies regex parsing in base class)
    pid = wp.project_id
    # It's okay if it's None in some fixtures, but it must be int if present
    assert pid is None or isinstance(pid, int)

    # Summary conversion
    s = wp.to_summary()
    assert s.subject == wp.subject
    assert s.status == wp.status_title
