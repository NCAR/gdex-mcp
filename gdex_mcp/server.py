"""GDEX MCP server — exposes GDEX dataset tools via the Model Context Protocol."""

import asyncio
import json
import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from gdex_mcp.client import GDEXClient

load_dotenv()

mcp = FastMCP("gdex")

_base_url = os.environ.get("GDEX_BASE_URL", "https://gdex.ucar.edu")
_token = os.environ.get("GDEX_TOKEN") or None
client = GDEXClient(_base_url, _token)


def _json(data) -> str:
    return json.dumps(data, indent=2, default=str)


async def _safe(coro):
    """Await a client call, turning an error into an inline result instead of raising."""
    try:
        return await coro
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Dataset discovery
# ---------------------------------------------------------------------------

_dataset_catalog: list[dict] | None = None
_dataset_catalog_lock = asyncio.Lock()


async def _get_dataset_catalog() -> list[dict]:
    """Return the full dataset catalog, fetched once per server process and cached.

    The catalog rarely changes within a session, and `list_datasets` may be
    called repeatedly with different queries — refetching and re-parsing all
    ~1700 entries every time would be wasteful.
    """
    global _dataset_catalog
    if _dataset_catalog is None:
        async with _dataset_catalog_lock:
            if _dataset_catalog is None:
                data = await client.list_datasets()
                _dataset_catalog = data["datasets"]
    return _dataset_catalog


@mcp.tool()
async def list_datasets(query: str = "", limit: int = 50, offset: int = 0) -> str:
    """List datasets available on GDEX, with their IDs and titles.

    The full catalog has ~1700 datasets — far too many to return at once.
    Always pass `query` to filter by keyword unless the user specifically
    wants to browse the whole catalog page by page.

    Args:
        query: Keyword(s) to filter by, matched case-insensitively as a substring
               against dataset id and title. Leave empty to browse unfiltered.
        limit: Max number of datasets to return (default 50, capped at 500)
        offset: Number of matching datasets to skip, for paging through results
    """
    datasets = await _get_dataset_catalog()
    if query:
        q = query.lower()
        datasets = [
            d
            for d in datasets
            if q in d.get("id", "").lower() or q in (d.get("title") or "").lower()
        ]
    total = len(datasets)
    limit = min(limit, 500)
    page = datasets[offset : offset + limit]
    return _json({"total_matches": total, "returned": len(page), "offset": offset, "datasets": page})


# ---------------------------------------------------------------------------
# Dataset metadata
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_dataset_metadata(dsid: str) -> str:
    """Return full metadata for a GDEX dataset (parameters, temporal range, spatial coverage, etc.).

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
    """
    data = await client.get_metadata(dsid)
    return _json(data)


@mcp.tool()
async def get_dataset_abstract(dsid: str) -> str:
    """Return the abstract / description text for a dataset.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
    """
    data = await client.get_abstract(dsid)
    return _json(data)


@mcp.tool()
async def get_dataset_variables(dsid: str) -> str:
    """Return the list of scientific variables contained in a dataset.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
    """
    data = await client.get_variables(dsid)
    return _json(data)


@mcp.tool()
async def get_dataset_temporal(dsid: str) -> str:
    """Return the temporal coverage (start/end dates) for a dataset.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
    """
    data = await client.get_temporal(dsid)
    return _json(data)


@mcp.tool()
async def get_dataset_spatial_coverage(dsid: str) -> str:
    """Return the spatial/geographic coverage for a dataset.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
    """
    data = await client.get_spatial_coverage(dsid)
    return _json(data)


@mcp.tool()
async def get_dataset_publications(dsid: str) -> str:
    """Return publications associated with a dataset.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
    """
    data = await client.get_publications(dsid)
    return _json(data)


@mcp.tool()
async def get_dataset_contributors(dsid: str) -> str:
    """Return the contributors (authors and organizations) for a dataset.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
    """
    data = await client.get_contributors(dsid)
    return _json(data)


@mcp.tool()
async def get_dataset_data_formats(dsid: str) -> str:
    """Return the available file formats for a dataset.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
    """
    data = await client.get_data_formats(dsid)
    return _json(data)


@mcp.tool()
async def get_dataset_volume(dsid: str) -> str:
    """Return the total data volume for a dataset.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
    """
    data = await client.get_volume(dsid)
    return _json(data)


@mcp.tool()
async def get_related_datasets(dsid: str) -> str:
    """Return datasets related to or derived from the given dataset.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
    """
    data = await client.get_related_datasets(dsid)
    return _json(data)


@mcp.tool()
async def get_dataset_documentation(dsid: str) -> str:
    """Return documentation links for a dataset.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
    """
    data = await client.get_documentation(dsid)
    return _json(data)


@mcp.tool()
async def describe_dataset(dsid: str) -> str:
    """Return a combined overview of a dataset — abstract, temporal coverage,
    spatial coverage, variables, data formats, and volume — in a single call.

    Prefer this over calling the individual get_dataset_* metadata tools one
    by one when the user wants a general summary of a dataset. If one of the
    underlying fields fails to load, it's returned as {"error": ...} rather
    than failing the whole call.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
    """
    abstract, temporal, spatial, variables, data_formats, volume = await asyncio.gather(
        _safe(client.get_abstract(dsid)),
        _safe(client.get_temporal(dsid)),
        _safe(client.get_spatial_coverage(dsid)),
        _safe(client.get_variables(dsid)),
        _safe(client.get_data_formats(dsid)),
        _safe(client.get_volume(dsid)),
    )
    return _json(
        {
            "abstract": abstract,
            "temporal": temporal,
            "spatial": spatial,
            "variables": variables,
            "data_formats": data_formats,
            "volume": volume,
        }
    )


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_file_groups(dsid: str, gindex: str = "") -> str:
    """Return file groups for a dataset. Pass gindex to get child groups under a parent.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
        gindex: Optional group index to fetch child groups
    """
    data = await client.get_file_groups(dsid, gindex or None)
    return _json(data)


@mcp.tool()
async def get_dataset_files(dsid: str, gindex: str = "") -> str:
    """Return a paginated file listing for a dataset or a specific group.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
        gindex: Optional group index to filter files
    """
    data = await client.get_dataset_files(dsid, gindex or None)
    return _json(data)


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_data_access(dsid: str) -> str:
    """Return data access options for a dataset — download links, Globus URLs, access methods.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
    """
    data = await client.get_data_access(dsid)
    return _json(data)


# ---------------------------------------------------------------------------
# ARCO (cloud-optimized data)
# ---------------------------------------------------------------------------


@mcp.tool()
async def has_arco(dsid: str) -> str:
    """Check whether Analysis-Ready Cloud-Optimized (ARCO) data is available for a dataset.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
    """
    data = await client.has_arco(dsid)
    return _json(data)


@mcp.tool()
async def get_arco_variables(dsid: str) -> str:
    """Return the list of ARCO variables available for a dataset.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
    """
    data = await client.get_arco_variables(dsid)
    return _json(data)


@mcp.tool()
async def search_arco_variables(dsid: str, query: str) -> str:
    """Search ARCO variables by name for a dataset.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
        query: Search text to match against variable names
    """
    data = await client.search_arco_variables(dsid, query)
    return _json(data)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

PORTAL_METRICS = (
    "volume_downloaded",
    "unique_users",
    "total_datasets",
    "total_citations",
    "gdex_volume",
    "total_requests",
    "top_datasets",
    "ai_datasets",
)

DATASET_METRICS = ("users_month", "users_year", "volume_month", "volume_year")


@mcp.tool()
async def get_portal_metrics(
    metric: str = "top_datasets",
) -> str:
    """Return a GDEX portal-wide metric.

    Args:
        metric: One of: volume_downloaded, unique_users, total_datasets,
                total_citations, gdex_volume, total_requests, top_datasets, ai_datasets
    """
    if metric not in PORTAL_METRICS:
        return f"Unknown metric '{metric}'. Valid options: {', '.join(PORTAL_METRICS)}"
    data = await client.get_portal_metric(metric)
    return _json(data)


@mcp.tool()
async def get_dataset_metrics(dsid: str, metric: str = "volume_year") -> str:
    """Return a per-dataset metric.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
        metric: One of: users_month, users_year, volume_month, volume_year
    """
    if metric not in DATASET_METRICS:
        return f"Unknown metric '{metric}'. Valid options: {', '.join(DATASET_METRICS)}"
    data = await client.get_dataset_metric(dsid, metric)
    return _json(data)


# ---------------------------------------------------------------------------
# Staff
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_staff(dsid: str = "") -> str:
    """Return GDEX staff contacts, optionally filtered to a specific dataset.

    Args:
        dsid: Optional dataset ID. If omitted, returns all staff.
    """
    data = await client.get_staff(dsid or None)
    return _json(data)


# ---------------------------------------------------------------------------
# Subsetting requests (require GDEX_TOKEN)
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_request_statuses() -> str:
    """List all subsetting request statuses for the authenticated user. Requires GDEX_TOKEN."""
    data = await client.list_request_statuses()
    return _json(data)


@mcp.tool()
async def check_request_status(rindex: str) -> str:
    """Check the status of a specific subsetting request. Requires GDEX_TOKEN.

    Args:
        rindex: Request index/ID
    """
    data = await client.check_request_status(rindex)
    return _json(data)


@mcp.tool()
async def get_request_files(rindex: str) -> str:
    """Return the output files for a completed subsetting request. Requires GDEX_TOKEN.

    Args:
        rindex: Request index/ID
    """
    data = await client.get_request_files(rindex)
    return _json(data)


@mcp.tool()
async def get_control_file_template(dsid: str) -> str:
    """Return the control file template for building a subsetting request for a dataset.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
    """
    data = await client.get_control_file_template(dsid)
    return _json(data)


def _parse_control_template(template_text: str) -> list[str]:
    """Extract field names (e.g. "dataset", "date", "param") from a GDEX
    control-file template's `key=value` lines, skipping blanks and comments."""
    fields = []
    for line in template_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key:
            fields.append(key)
    return fields


@mcp.tool()
async def validate_subset_request(dsid: str, request_json: str) -> str:
    """Check a subset request body against the dataset's control file template,
    without submitting anything. Use this before submit_subset_request to catch
    missing or unrecognized fields fast, instead of finding out from a failed
    API call.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
        request_json: JSON string of the subsetting request body to validate
    """
    try:
        body = json.loads(request_json)
    except json.JSONDecodeError as e:
        return _json({"valid": False, "errors": [f"Invalid JSON: {e}"], "warnings": []})
    if not isinstance(body, dict):
        return _json({"valid": False, "errors": ["Request body must be a JSON object"], "warnings": []})

    template = await client.get_control_file_template(dsid)
    expected_fields = _parse_control_template(template.get("template", ""))

    missing = [f for f in expected_fields if f not in body and f != "groupindex"]
    unknown = [k for k in body if k not in expected_fields]

    errors = [f"Missing expected field: {f}" for f in missing]
    warnings = [f"Field not present in this dataset's template: {k}" for k in unknown]

    return _json(
        {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "expected_fields": expected_fields,
        }
    )


@mcp.tool()
async def submit_subset_request(request_json: str) -> str:
    """Submit a data subset request to GDEX. Requires GDEX_TOKEN.

    Args:
        request_json: JSON string of the subsetting request body. Use get_control_file_template
                      to get the expected structure for a dataset, or validate_subset_request
                      to check it before submitting.
    """
    try:
        body = json.loads(request_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"
    data = await client.submit_subset_request(body)
    return _json(data)


@mcp.tool()
async def purge_request(rindex: str) -> str:
    """Delete a subsetting request and its output files. Requires GDEX_TOKEN.

    Args:
        rindex: Request index/ID to purge
    """
    data = await client.purge_request(rindex)
    return _json(data)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    mcp.run()


if __name__ == "__main__":
    main()
