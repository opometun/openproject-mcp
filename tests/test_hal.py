from openproject_mcp.hal import (
    get_embedded,
    get_link,
    get_link_href,
    get_link_title,
    parse_id_from_href,
    resolve_property,
)


def test_get_link_basic_cases():
    assert get_link({"id": 1}, "status") is None
    payload = {"_links": {"status": {"href": "/api/v3/statuses/1", "title": "Open"}}}
    assert get_link(payload, "status") == {
        "href": "/api/v3/statuses/1",
        "title": "Open",
    }
    assert get_link(payload, "missing") is None


def test_get_link_href_and_title():
    payload = {
        "_links": {
            "self": {"href": "/api/v3/work_packages/1"},
            "status": {"href": "/api/v3/statuses/1", "title": "In Progress"},
        }
    }
    assert get_link_href(payload, "self") == "/api/v3/work_packages/1"
    assert get_link_title(payload, "status") == "In Progress"
    assert get_link_href(payload, "nope") is None
    assert get_link_title(payload, "nope") is None


def test_get_embedded_cases():
    assert get_embedded({"id": 2}, "status") is None
    emb = {"_embedded": {"status": {"id": 1, "name": "Closed"}}}
    assert get_embedded(emb, "status") == {"id": 1, "name": "Closed"}


def test_parse_id_from_href_various():
    assert parse_id_from_href("/api/v3/work_packages/42") == 42
    assert parse_id_from_href("/api/v3/projects/100/") == 100
    assert parse_id_from_href("/api/v3/items/not-an-int") is None
    assert parse_id_from_href(None) is None
    assert parse_id_from_href("") is None


def test_resolve_property_priority_and_fallbacks():
    payload = {
        "subject": "Root Subject",
        "_links": {"subject": {"title": "Link Subject"}},
        "_embedded": {"subject": {"value": "Embedded Subject"}},
    }
    assert resolve_property(payload, "subject") == "Root Subject"

    payload2 = {
        "_links": {"status": {"title": "Link Status"}},
        "_embedded": {"status": {"id": 7, "name": "Embedded Status"}},
    }
    assert resolve_property(payload2, "status") == "Link Status"

    payload3 = {"_embedded": {"priority": {"id": 3, "name": "High"}}}
    assert resolve_property(payload3, "priority") == {"id": 3, "name": "High"}

    assert resolve_property({}, "missing") is None
