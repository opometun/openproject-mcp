import json
from pathlib import Path


def test_fixtures_are_valid_json():
    """Ensure we can load our sample data."""
    fixtures_dir = Path(__file__).parent / "fixtures"

    # Check Project List
    with open(fixtures_dir / "project_list.json") as f:
        data = json.load(f)
        assert data["_type"] == "Collection"
        assert len(data["_embedded"]["elements"]) >= 1

    # Check Work Package
    with open(fixtures_dir / "work_package.json") as f:
        data = json.load(f)
        assert data["_type"] == "WorkPackageCollection"
        assert data["_embedded"]["elements"][0]["id"] == 10001
