import httpx
import pytest

from gdex_mcp.client import (
    GDEXAuthError,
    GDEXClient,
    GDEXError,
    GDEXNotFoundError,
    GDEXValidationError,
    _classify_message,
    _rewrite_arco_zarr_urls,
)

from .conftest import run


def test_headers_with_and_without_token():
    assert "Authorization" not in GDEXClient("https://x")._headers()
    assert GDEXClient("https://x", "abc")._headers()["Authorization"] == "Token abc"


def test_base_url_trailing_slash_stripped():
    assert GDEXClient("https://x/").base_url == "https://x"


def test_unwrap_returns_data_and_raises_on_error():
    c = GDEXClient("https://x")
    assert c._unwrap({"status": "success", "data": {"a": 1}}) == {"a": 1}
    with pytest.raises(GDEXError, match="boom"):
        c._unwrap({"status": "error", "error_messages": ["boom"]})


@pytest.mark.parametrize(
    "message,cls",
    [
        ("Invalid token", GDEXAuthError),
        ("Dataset not found", GDEXNotFoundError),
        ("something else", GDEXError),
    ],
)
def test_classify_message(message, cls):
    assert _classify_message(message) is cls


@pytest.mark.parametrize(
    "status,cls",
    [
        (401, GDEXAuthError),
        (403, GDEXAuthError),
        (404, GDEXNotFoundError),
        (400, GDEXValidationError),
        (422, GDEXValidationError),
        (500, GDEXError),
    ],
)
def test_http_status_classification(mock_gdex, status, cls):
    mock_gdex(lambda r: httpx.Response(status, json={"detail": "nope"}))
    with pytest.raises(cls) as ei:
        run(GDEXClient("https://gdex.test")._get("/api/x/"))
    assert type(ei.value) is cls


def test_non_json_error_body(mock_gdex):
    mock_gdex(lambda r: httpx.Response(502, text="<html>bad gateway</html>"))
    with pytest.raises(GDEXError, match="HTTP 502"):
        run(GDEXClient("https://gdex.test")._get("/api/x/"))


def test_get_drops_none_params_and_sends_token(mock_gdex):
    mock_gdex(lambda r: httpx.Response(200, json={"status": "success", "data": {"ok": True}}))
    out = run(GDEXClient("https://gdex.test", "tok")._get("/api/x/", a="1", b=None))
    assert out == {"ok": True}
    req = mock_gdex.requests[0]
    assert dict(req.url.params) == {"a": "1"}
    assert req.headers["authorization"] == "Token tok"


def test_error_envelope_on_200(mock_gdex):
    mock_gdex(lambda r: httpx.Response(200, json={"status": "error", "error_messages": ["Not found"]}))
    with pytest.raises(GDEXNotFoundError):
        run(GDEXClient("https://gdex.test")._get("/api/x/"))


def test_rewrite_arco_zarr_urls():
    rows = [
        ["https://data.gdex.ucar.edu/a.zarr", "v", "zarr"],
        ["https://data.gdex.ucar.edu/a.json", "v", "reference"],
    ]
    out = _rewrite_arco_zarr_urls(rows)
    assert out[0][0] == "https://osdf-director.osg-htc.org/ncar/gdex/a.zarr"
    assert out[1] == rows[1]
    assert _rewrite_arco_zarr_urls({"error": "x"}) == {"error": "x"}
