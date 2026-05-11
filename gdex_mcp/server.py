"""GDEX MCP server — exposes GDEX dataset tools via the Model Context Protocol."""

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


# ---------------------------------------------------------------------------
# Dataset discovery
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_datasets() -> str:
    """List all datasets available on GDEX with their IDs and titles."""
    data = await client.list_datasets()
    return _json(data)


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


@mcp.tool()
async def submit_subset_request(request_json: str) -> str:
    """Submit a data subset request to GDEX. Requires GDEX_TOKEN.

    Args:
        request_json: JSON string of the subsetting request body. Use get_control_file_template
                      to get the expected structure for a dataset.
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
