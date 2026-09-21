import json

import httpx
import pytest

from gdex_mcp import server
from gdex_mcp.client import GDEXAuthError, GDEXError

from .conftest import run


def test_json_is_compact():
    assert server._json({"a": [1, 2]}) == '{"a":[1,2]}'


def test_safe_reports_error_type():
    async def bad():
        raise GDEXAuthError("no token")

    async def worse():
        raise ValueError("oops")

    async def good():
        return {"ok": 1}

    assert run(server._safe(bad())) == {"error": "no token", "error_type": "GDEXAuthError"}
    assert run(server._safe(worse())) == {"error": "oops"}
    assert run(server._safe(good())) == {"ok": 1}


def test_authed_client_prefers_request_token(monkeypatch):
    monkeypatch.setattr(server, "_token", "env-token")
    assert server._authed_client().token == "env-token"
    reset = server._request_token.set("caller-token")
    try:
        assert server._authed_client().token == "caller-token"
    finally:
        server._request_token.reset(reset)


def test_metric_and_field_validation_never_hits_api():
    assert "Unknown metric" in run(server.get_portal_metrics("bogus"))
    assert "Unknown metric" in run(server.get_dataset_metrics("d083002", "bogus"))
    assert "Unknown field" in run(server.get_dataset_field("d083002", "bogus"))


def test_dataset_fields_cover_documented_names():
    assert set(server.DATASET_FIELDS) == {
        "abstract", "variables", "temporal", "spatial_coverage", "publications",
        "contributors", "data_formats", "volume", "related_datasets", "documentation",
    }


def test_list_datasets_filter_and_paging(monkeypatch):
    catalog = [{"id": f"d00000{i}", "title": "Wind" if i % 2 else "Rain"} for i in range(6)]
    monkeypatch.setattr(server, "_dataset_catalog", catalog)
    out = json.loads(run(server.list_datasets(query="wind", limit=2, offset=1)))
    assert out["total_matches"] == 3
    assert out["returned"] == 2
    assert all(d["title"] == "Wind" for d in out["datasets"])


def test_cap_dataset_files_truncates_across_groups():
    data = {"groups": [{"rows": list(range(3))}, {"rows": list(range(3))}]}
    out = server._cap_dataset_files(data, cap=4)
    assert out["_truncated"] is True
    assert [len(g["rows"]) for g in out["groups"]] == [3, 1]
    assert server._cap_dataset_files(data, cap=10) is data
    assert server._cap_dataset_files({"x": 1}) == {"x": 1}


def test_cap_arco_variables():
    rows = [[str(i)] for i in range(5)]
    assert server._cap_arco_variables(rows, cap=10) is rows
    out = server._cap_arco_variables(rows, cap=2)
    assert out["truncated"] and out["total"] == 5 and len(out["variables"]) == 2
    assert server._cap_arco_variables({"error": "x"}) == {"error": "x"}


def test_parse_control_template():
    text = "# comment\n\ndataset=d083002\n date = x\nnoequals\n"
    assert server._parse_control_template(text) == ["dataset", "date"]


def test_extract_rindex():
    assert server._extract_rindex({"rindex": 42}) == "42"
    assert server._extract_rindex({"request_index": "7"}) == "7"
    assert server._extract_rindex({"nope": 1}) is None


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"status": "Completed"}, "ok"),
        ({"state": "Error: bad"}, "failed"),
        ({"status": "Queued"}, "pending"),
        ({}, "pending"),
        ({"status": 5}, "pending"),
    ],
)
def test_classify_status(payload, expected):
    assert server._classify_status(payload) == expected


def test_validate_subset_request(mock_gdex, monkeypatch):
    monkeypatch.setattr(server, "client", server.GDEXClient("https://gdex.test"))
    mock_gdex(
        lambda r: httpx.Response(
            200, json={"status": "success", "data": {"template": "dataset=\ndate=\ngroupindex=\n"}}
        )
    )
    ok = json.loads(run(server.validate_subset_request("d083002", '{"dataset":"d","date":"x"}')))
    assert ok["valid"] and ok["warnings"] == []
    bad = json.loads(run(server.validate_subset_request("d083002", '{"dataset":"d","extra":1}')))
    assert not bad["valid"]
    assert "Missing expected field: date" in bad["errors"]
    assert any("extra" in w for w in bad["warnings"])


def test_validate_subset_request_bad_input():
    assert json.loads(run(server.validate_subset_request("d1", "{nope")))["valid"] is False
    assert json.loads(run(server.validate_subset_request("d1", "[1]")))["valid"] is False


def test_auth_tool_returns_structured_error(mock_gdex, monkeypatch):
    monkeypatch.setattr(server, "_token", None)
    mock_gdex(lambda r: httpx.Response(401, json={"detail": "Invalid token."}))
    out = json.loads(run(server.list_request_statuses()))
    assert out["error_type"] == "GDEXAuthError"


def test_submit_rejects_invalid_json():
    assert run(server.submit_subset_request("{bad")).startswith("Invalid JSON")


def test_bearer_middleware_extracts_token():
    seen = {}

    async def app(scope, receive, send):
        seen["token"] = server._request_token.get()

    mw = server._BearerTokenMiddleware(app)
    run(mw({"type": "http", "headers": [(b"authorization", b"Token abc123")]}, None, None))
    assert seen["token"] == "abc123"
    run(mw({"type": "http", "headers": [(b"authorization", b"Bearer xyz")]}, None, None))
    assert seen["token"] == "xyz"
    run(mw({"type": "http", "headers": []}, None, None))
    assert seen["token"] is None
    assert server._request_token.get() is None  # reset after request


def test_main_rejects_unknown_transport(monkeypatch):
    monkeypatch.setenv("GDEX_MCP_TRANSPORT", "carrier-pigeon")
    with pytest.raises(ValueError, match="carrier-pigeon"):
        server.main()


def test_transport_security_allows_configured_host(monkeypatch):
    from mcp.server.transport_security import TransportSecurityMiddleware

    monkeypatch.setenv("GDEX_MCP_ALLOWED_HOSTS", "gdex-mcp.k8s.ucar.edu")
    mw = TransportSecurityMiddleware(server._transport_security())
    assert mw._validate_host("gdex-mcp.k8s.ucar.edu")
    assert mw._validate_host("gdex-mcp.k8s.ucar.edu:443")
    assert mw._validate_host("localhost:8080")
    assert not mw._validate_host("evil.example.com")


def test_transport_security_defaults_to_localhost_only(monkeypatch):
    from mcp.server.transport_security import TransportSecurityMiddleware

    monkeypatch.delenv("GDEX_MCP_ALLOWED_HOSTS", raising=False)
    mw = TransportSecurityMiddleware(server._transport_security())
    assert mw._validate_host("127.0.0.1:8080")
    assert not mw._validate_host("gdex-mcp.k8s.ucar.edu")
