"""GDEX MCP server — exposes GDEX dataset tools via the Model Context Protocol."""

import asyncio
import json
import os
import time

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from gdex_mcp.client import GDEXAuthError, GDEXClient, GDEXError

load_dotenv()

mcp = FastMCP("gdex")

_base_url = os.environ.get("GDEX_BASE_URL", "https://gdex.ucar.edu")
_token = os.environ.get("GDEX_TOKEN") or None
client = GDEXClient(_base_url, _token)


def _json(data) -> str:
    return json.dumps(data, indent=2, default=str)


async def _safe(coro):
    """Await a client call, turning an error into an inline result instead of raising.

    Includes `error_type` (the GDEXError subclass name, e.g. "GDEXAuthError")
    whenever the failure came from the GDEX client, so callers — human or
    model — can tell "you're not logged in" apart from "that ID doesn't
    exist" without parsing the message text.
    """
    try:
        return await coro
    except GDEXError as e:
        return {"error": str(e), "error_type": type(e).__name__}
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


async def _describe_dataset_data(dsid: str) -> dict:
    """Fetch the combined-overview fields for a dataset. Shared by the
    describe_dataset tool and the gdex://dataset/{dsid} resource so the two
    stay in sync rather than drifting into two slightly different summaries."""
    abstract, temporal, spatial, variables, data_formats, volume = await asyncio.gather(
        _safe(client.get_abstract(dsid)),
        _safe(client.get_temporal(dsid)),
        _safe(client.get_spatial_coverage(dsid)),
        _safe(client.get_variables(dsid)),
        _safe(client.get_data_formats(dsid)),
        _safe(client.get_volume(dsid)),
    )
    return {
        "dsid": dsid,
        "abstract": abstract,
        "temporal": temporal,
        "spatial": spatial,
        "variables": variables,
        "data_formats": data_formats,
        "volume": volume,
    }


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
    return _json(await _describe_dataset_data(dsid))


@mcp.resource(
    "gdex://dataset/{dsid}",
    name="Dataset overview",
    description="Combined overview of one GDEX dataset — abstract, temporal/spatial "
    "coverage, variables, data formats, volume. Same content as describe_dataset.",
    mime_type="application/json",
)
async def dataset_resource(dsid: str) -> str:
    return _json(await _describe_dataset_data(dsid))


@mcp.resource(
    "gdex://datasets",
    name="Dataset catalog",
    description="Full GDEX dataset catalog (~1700 entries) as id/title pairs. "
    "Prefer the list_datasets tool for keyword-filtered lookups; this resource "
    "is for clients that want the whole catalog as attachable context.",
    mime_type="application/json",
)
async def datasets_resource() -> str:
    datasets = await _get_dataset_catalog()
    return _json({"total": len(datasets), "datasets": datasets})


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_file_groups(dsid: str, gindex: str = "") -> str:
    """Return file groups for a dataset. Pass gindex to get child groups under a parent.

    Groups nest (dataset -> format -> year -> month, or similar, varying by
    dataset) and there's no way to predict a child's gindex in advance — each
    group's gindex/url is dataset-specific and only knowable from the parent
    response. To drill down, read the gindex (or url) off a row in this
    response and pass that as the next call's gindex.

    This never returns file rows, only groups — every response stays small
    regardless of how many files the dataset holds, unlike get_dataset_files.
    Descend until a call returns empty ({} or []): that means the gindex you
    just called with is a leaf with no further subgroups, so it's safe to
    call get_dataset_files there for the actual files. find_dataset_files
    automates exactly this walk if you'd rather not do it by hand.

    At the top level, watch for a "Kerchunk Reference Files" (or similar
    ARCO-related) group alongside the raw-format groups. For an analysis
    task, prefer pulling from there (see also has_arco/get_arco_variables)
    over a raw data file when one's available — it avoids downloading a
    whole file just to read a subset of it.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
        gindex: Optional group index to fetch child groups
    """
    data = await client.get_file_groups(dsid, gindex or None)
    return _json(data)


@mcp.tool()
async def get_dataset_files(
    dsid: str, gindex: str = "", page: int = 0, filter_wfile: str = "", fl: str = ""
) -> str:
    """Return a paginated file listing for a dataset or a specific group.

    Depending on how deep gindex is in the group hierarchy, this returns
    either actual file rows or another layer of subgroup summaries — there's
    no way to tell in advance which you'll get. If you get subgroups, read
    the gindex (or url) off a row and call again with that gindex to go one
    level deeper; gindex values are dataset-specific and can't be guessed.

    A shallow gindex on a large dataset can return a very large response
    (thousands of files). Two ways to avoid that instead of drilling down
    group by group: pass filter_wfile with a filename pattern (e.g. a date
    like "20220808") to filter down to matching files, or page through a
    known group's results with `page`. filter_wfile only filters actual file
    rows, so it has no effect at a gindex that's still returning a subgroup
    summary rather than files — if a first attempt comes back unfiltered,
    descend one level (see get_file_groups) and retry there.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
        gindex: Optional group index to filter files
        page: Page number to fetch (for a group with more files than fit on one page)
        filter_wfile: Filter files by name pattern, e.g. "20220808" to match a date
        fl: File list source (defaults to "web" server-side)
    """
    data = await client.get_dataset_files(
        dsid,
        gindex or None,
        page or None,
        filter_wfile or None,
        fl or None,
    )
    return _json(data)


def _flatten_file_rows(filelist_response) -> list[dict]:
    """Flatten a get_dataset_files response's nested column/row shape (each
    file is a list of {"name": <column>, "value": ...} cells) into a list of
    plain {column_name: value} dicts, one per file. Column names vary by
    dataset, so this reads whatever's there rather than assuming a fixed set.
    Non-file rows are skipped, but find_dataset_files only calls this on
    responses from gindexes get_file_groups already confirmed are leaves, so
    that shouldn't come up in practice."""
    rows_out = []
    if not isinstance(filelist_response, dict):
        return rows_out
    for group in filelist_response.get("groups", []):
        for row in group.get("rows", []):
            cell_by_name = {}
            is_file = False
            for cell in row:
                name = cell.get("name")
                if name:
                    cell_by_name[name] = cell.get("value")
                if cell.get("is_file"):
                    is_file = True
                    if cell.get("url"):
                        cell_by_name["download_url"] = cell["url"]
            if is_file:
                rows_out.append(cell_by_name)
    return rows_out


@mcp.tool()
async def find_dataset_files(
    dsid: str, name_pattern: str, start_gindex: str = "", max_groups_visited: int = 300
) -> str:
    """Search a dataset's file-group hierarchy for files matching a name
    pattern (e.g. a date like "20220808"), without ever pulling a large,
    context-blowing file listing.

    Automates the pattern described in get_file_groups: recursively calls
    get_file_groups, descending into every child gindex, until a gindex
    returns no further children (a leaf group) — then calls get_dataset_files
    there with filter_wfile=name_pattern and keeps only the matches. Prefer
    this over manually drilling with get_file_groups/get_dataset_files when
    you don't already know roughly where in the hierarchy to look.

    A dataset's hierarchy can be large (hundreds of leaf groups), and this
    tool has no way to know in advance which branches might contain a match,
    so it may need to visit many groups to be thorough. Pass start_gindex if
    you already know a good starting point (e.g. from a prior get_file_groups
    call, or a related dataset's structure) to narrow and speed up the
    search. If the number of groups visited hits max_groups_visited, the
    search stops early and `stopped_early` comes back true — narrow with
    start_gindex and retry, or raise the cap.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
        name_pattern: Filename substring/pattern to match, e.g. "20220808" for a date
        start_gindex: Optional group index to start the search from, instead of the dataset root
        max_groups_visited: Safety cap on groups traversed before giving up (default 300)
    """
    max_groups_visited = max(1, min(max_groups_visited, 5000))
    state = {"visited": 0, "stopped_early": False}
    matches: list[dict] = []
    errors: list[dict] = []
    # The recursion below fans out concurrently at every level (asyncio.gather
    # over each group's children) — without a cap, a wide hierarchy can fire
    # off far more simultaneous requests than the connection pool/server can
    # handle, and a resulting connection error would otherwise take the whole
    # crawl down with it (see the (GDEXError, httpx.HTTPError) catch below).
    semaphore = asyncio.Semaphore(5)

    async def visit(gindex: str | None) -> None:
        if state["stopped_early"]:
            return
        if state["visited"] >= max_groups_visited:
            state["stopped_early"] = True
            return
        state["visited"] += 1
        try:
            async with semaphore:
                children = await client.get_file_groups(dsid, gindex)
        except (GDEXError, httpx.HTTPError) as e:
            errors.append({"gindex": gindex, "error": str(e), "error_type": type(e).__name__})
            return

        if not children:
            # Empty response -> gindex is a leaf (see get_file_groups) -> safe to
            # pull its (filtered) file listing.
            try:
                async with semaphore:
                    filelist = await client.get_dataset_files(dsid, gindex, filter_wfile=name_pattern)
            except (GDEXError, httpx.HTTPError) as e:
                errors.append({"gindex": gindex, "error": str(e), "error_type": type(e).__name__})
                return
            matches.extend(_flatten_file_rows(filelist))
            return

        await asyncio.gather(*(visit(str(child["gindex"])) for child in children if "gindex" in child))

    await visit(start_gindex or None)

    return _json(
        {
            "dsid": dsid,
            "name_pattern": name_pattern,
            "groups_visited": state["visited"],
            "stopped_early": state["stopped_early"],
            "match_count": len(matches),
            "matches": matches,
            "errors": errors,
        }
    )


# --- File search ---
#
# A content-based alternative to get_dataset_files/get_file_groups: instead of
# browsing file groups, search for files containing a specific datatype
# (grid, cyclone_fix, sensor), optionally filtered by time range and — for
# grid — parameter/product/grid/level codes. Not every dataset supports every
# datatype; call get_filesearch_datatypes first to see which apply.


@mcp.tool()
async def get_filesearch_datatypes(dsid: str) -> str:
    """Return the file-search datatypes available for a dataset (a subset of
    "grid", "cyclone_fix", "sensor"). Call this before the other filesearch_*
    tools to know which one(s) apply — a dataset only supports search for the
    datatypes it actually contains.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
    """
    data = await client.get_filesearch_datatypes(dsid)
    return _json(data)


@mcp.tool()
async def get_filesearch_grid_filters(
    dsid: str,
    valid_datetime_min: str = "",
    valid_datetime_max: str = "",
    parameters: list[str] = [],
    products: list[str] = [],
    grids: list[str] = [],
    levels: list[str] = [],
) -> str:
    """Return the valid parameter/product/grid/level codes and date range for
    "grid" datatype file search on a dataset. Use this to discover the codes
    to pass to get_filesearch_grid_files, optionally narrowed by any filters
    you already know you want.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
        valid_datetime_min: Restrict to data valid on/after "YYYY-MM-DD HH:MM"
        valid_datetime_max: Restrict to data valid on/before "YYYY-MM-DD HH:MM"
        parameters: Restrict to specified parameter code(s)
        products: Restrict to specified product code(s)
        grids: Restrict to specified grid code(s)
        levels: Restrict to specified vertical level code(s)
    """
    data = await client.get_filesearch_grid_filters(
        dsid,
        valid_datetime_min=valid_datetime_min or None,
        valid_datetime_max=valid_datetime_max or None,
        parameters=parameters or None,
        products=products or None,
        grids=grids or None,
        levels=levels or None,
    )
    return _json(data)


@mcp.tool()
async def get_filesearch_cyclone_fix_filters(
    dsid: str, valid_datetime_min: str = "", valid_datetime_max: str = ""
) -> str:
    """Return the valid date range and other filters for "cyclone_fix"
    datatype file search on a dataset.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
        valid_datetime_min: Restrict to data valid on/after "YYYY-MM-DD HH:MM"
        valid_datetime_max: Restrict to data valid on/before "YYYY-MM-DD HH:MM"
    """
    data = await client.get_filesearch_cyclone_fix_filters(
        dsid,
        valid_datetime_min=valid_datetime_min or None,
        valid_datetime_max=valid_datetime_max or None,
    )
    return _json(data)


@mcp.tool()
async def get_filesearch_sensor_filters(dsid: str, valid_date_min: str = "", valid_date_max: str = "") -> str:
    """Return the valid date range and other filters for "sensor" datatype
    file search on a dataset.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
        valid_date_min: Restrict to data valid on/after "YYYY-MM-DD"
        valid_date_max: Restrict to data valid on/before "YYYY-MM-DD"
    """
    data = await client.get_filesearch_sensor_filters(
        dsid,
        valid_date_min=valid_date_min or None,
        valid_date_max=valid_date_max or None,
    )
    return _json(data)


@mcp.tool()
async def get_filesearch_grid_files(
    dsid: str,
    parameters: list[str],
    valid_datetime_min: str = "",
    valid_datetime_max: str = "",
    products: list[str] = [],
    grids: list[str] = [],
    levels: list[str] = [],
) -> str:
    """Search for data files containing "grid" datatype data, filtered by
    parameter code(s) and optionally by time range, product, grid, or level.
    Results are paginated; use get_filesearch_result_page with the returned
    result_id to fetch additional pages. Use get_filesearch_grid_filters
    first to find valid parameter/product/grid/level codes for this dataset.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
        parameters: Parameter code(s) to search for (required, at least one)
        valid_datetime_min: Restrict to data valid on/after "YYYY-MM-DD HH:MM"
        valid_datetime_max: Restrict to data valid on/before "YYYY-MM-DD HH:MM"
        products: Restrict to specified product code(s)
        grids: Restrict to specified grid code(s)
        levels: Restrict to specified vertical level code(s)
    """
    data = await client.get_filesearch_grid_files(
        dsid,
        parameters,
        valid_datetime_min=valid_datetime_min or None,
        valid_datetime_max=valid_datetime_max or None,
        products=products or None,
        grids=grids or None,
        levels=levels or None,
    )
    return _json(data)


@mcp.tool()
async def get_filesearch_cyclone_fix_files(
    dsid: str, valid_datetime_min: str = "", valid_datetime_max: str = ""
) -> str:
    """Search for data files containing "cyclone_fix" datatype data, optionally
    filtered by time range. Results are paginated; use get_filesearch_result_page
    with the returned result_id to fetch additional pages.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
        valid_datetime_min: Restrict to data valid on/after "YYYY-MM-DD HH:MM"
        valid_datetime_max: Restrict to data valid on/before "YYYY-MM-DD HH:MM"
    """
    data = await client.get_filesearch_cyclone_fix_files(
        dsid,
        valid_datetime_min=valid_datetime_min or None,
        valid_datetime_max=valid_datetime_max or None,
    )
    return _json(data)


@mcp.tool()
async def get_filesearch_sensor_files(dsid: str, valid_date_min: str = "", valid_date_max: str = "") -> str:
    """Search for data files containing "sensor" datatype data, optionally
    filtered by date range. Results are paginated; use get_filesearch_result_page
    with the returned result_id to fetch additional pages.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
        valid_date_min: Restrict to data valid on/after "YYYY-MM-DD"
        valid_date_max: Restrict to data valid on/before "YYYY-MM-DD"
    """
    data = await client.get_filesearch_sensor_files(
        dsid,
        valid_date_min=valid_date_min or None,
        valid_date_max=valid_date_max or None,
    )
    return _json(data)


@mcp.tool()
async def get_filesearch_result_page(dsid: str, result_id: str, page_num: int) -> str:
    """Return a page of results from a previous get_filesearch_*_files call, by
    its result_id. Use this to page through file-search results beyond the
    first page (see the "pagination" block of a files/results response for
    num_pages and next_page).

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
        result_id: The result_id from a previous filesearch files/results response
        page_num: Page number to retrieve
    """
    data = await client.get_filesearch_result_page(dsid, result_id, page_num)
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
#
# Many datasets also expose a "Kerchunk Reference Files" file group (see
# get_file_groups) alongside or instead of ARCO variables — reference files
# that let clients (e.g. via xarray) read subsets of the underlying data
# without downloading whole raw files. When a task is analysis rather than
# "give me the raw file", check has_arco / look for a Kerchunk Reference
# Files group first and prefer that over pulling full data files.
#
# A given variable is often published as several kerchunk reference variants
# (e.g. "<name>.parq", "<name>-remote-https.parq", "<name>-remote-osdf.parq").
# ALWAYS pick the variant with "-osdf" in its name — the others' chunk
# targets can be internal filesystem paths (e.g. /gpfs/...) that only
# resolve on NCAR's own network and raise ReferenceNotReachable everywhere
# else, while "-osdf" targets go through the Open Science Data Federation
# and are reachable from anywhere.
#
# To open one, prefer xarray's dedicated kerchunk backend over hand-rolling
# an fsspec "reference" filesystem — it's better behaved (e.g. avoids a
# zarr-v3/fsspec async-store incompatibility the manual route hits):
#
#     xr.open_dataset(url, engine="kerchunk",
#                      storage_options={"remote_protocol": "https", "lazy": True})
#
# This needs the `kerchunk` and `fastparquet` packages installed (parquet-
# backed reference sets use fastparquet, not pyarrow, under the hood).
# ---------------------------------------------------------------------------


@mcp.tool()
async def has_arco(dsid: str) -> str:
    """Check whether Analysis-Ready Cloud-Optimized (ARCO) data is available for a dataset.

    For analysis tasks, call this (and check for a "Kerchunk Reference Files"
    group via get_file_groups) before reaching for raw data files — reading
    through ARCO/kerchunk references avoids downloading whole files just to
    subset them. When picking among kerchunk reference variants, always use
    the one with "-osdf" in its name (see get_arco_variables) — other
    variants' chunk targets can be internal paths that only resolve on
    NCAR's network. Open it with xr.open_dataset(url, engine="kerchunk",
    storage_options={"remote_protocol": "https", "lazy": True}) rather than
    hand-building an fsspec reference filesystem.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
    """
    data = await client.has_arco(dsid)
    return _json(data)


@mcp.tool()
async def get_arco_variables(dsid: str) -> str:
    """Return the list of ARCO variables available for a dataset.

    A variable is often listed multiple times, once per kerchunk reference
    variant (plain, "-remote-https", "-remote-osdf", etc.). Always pick the
    "-osdf" variant's URL — it's reachable from anywhere; the others' chunk
    targets can be internal paths that only resolve on NCAR's network. Open
    the chosen URL with xr.open_dataset(url, engine="kerchunk",
    storage_options={"remote_protocol": "https", "lazy": True}) — that's
    better behaved than hand-building an fsspec reference filesystem.

    Args:
        dsid: Dataset ID in dNNNNNN format, e.g. d083002
    """
    data = await client.get_arco_variables(dsid)
    return _json(data)


@mcp.tool()
async def search_arco_variables(dsid: str, query: str) -> str:
    """Search ARCO variables by name for a dataset.

    As with get_arco_variables, a match is often listed once per kerchunk
    reference variant — always pick the "-osdf" variant's URL (reachable
    from anywhere), and open it with xr.open_dataset(url, engine="kerchunk",
    storage_options={"remote_protocol": "https", "lazy": True}).

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


# GDEX's schema doesn't document field names/values for the submit response or
# the status payload, so the helpers below are deliberately tolerant: they try
# a handful of plausible key names and fall back to "we don't know" rather
# than guessing wrong. If your GDEX instance uses different wording, these are
# the only places that need to change.
_RINDEX_KEYS = ("rindex", "request_index", "requestIndex", "index", "id")
_STATUS_KEYS = ("status", "state", "request_status", "requestStatus")
_STATUS_OK_MARKERS = ("complete", "finished", "done", "ready", "success")
_STATUS_FAILED_MARKERS = ("error", "fail", "purged", "cancel", "reject")


def _extract_rindex(submit_response: dict) -> str | None:
    for key in _RINDEX_KEYS:
        if key in submit_response:
            return str(submit_response[key])
    return None


def _classify_status(status_response: dict) -> str:
    """Best-effort read of a status payload: "ok", "failed", or "pending"
    (including the case where we can't even find a status string)."""
    status_str = None
    for key in _STATUS_KEYS:
        val = status_response.get(key)
        if isinstance(val, str):
            status_str = val
            break
    if not status_str:
        return "pending"
    s = status_str.lower()
    if any(m in s for m in _STATUS_FAILED_MARKERS):
        return "failed"
    if any(m in s for m in _STATUS_OK_MARKERS):
        return "ok"
    return "pending"


@mcp.tool()
async def submit_and_wait_for_request(
    request_json: str, poll_interval_s: int = 15, timeout_s: int = 600
) -> str:
    """Submit a subset request and poll its status until it finishes, fails, or
    timeout_s elapses — instead of calling submit_subset_request and then
    manually looping on check_request_status. Requires GDEX_TOKEN.

    GDEX's API schema doesn't document the exact status vocabulary, so
    "finished" is a best-effort match on the status text (words like
    "complete" vs. "error"/"fail"). If the outcome comes back "timeout", that
    means the request is still pending by our reading, not that it failed —
    keep polling with check_request_status(rindex), or re-run this tool with
    a longer timeout_s. If it comes back "unknown", the status payload didn't
    contain a field we recognize; inspect the raw "status" value yourself.

    Args:
        request_json: JSON string of the subsetting request body (see get_control_file_template).
        poll_interval_s: Seconds between status checks (default 15, minimum 5).
        timeout_s: Give up and return the last-seen status after this many seconds (default 600).
    """
    try:
        body = json.loads(request_json)
    except json.JSONDecodeError as e:
        return _json({"outcome": "error", "error": f"Invalid JSON: {e}"})

    try:
        submit_response = await client.submit_subset_request(body)
    except GDEXError as e:
        return _json({"outcome": "error", "error": str(e), "error_type": type(e).__name__})

    rindex = _extract_rindex(submit_response)
    if rindex is None:
        return _json(
            {
                "outcome": "error",
                "error": "Could not find a request index in the submit response — "
                "none of "
                f"{_RINDEX_KEYS} were present. Inspect submit_response and use "
                "check_request_status manually.",
                "submit_response": submit_response,
            }
        )

    poll_interval_s = max(poll_interval_s, 5)
    deadline = time.monotonic() + timeout_s
    status_response: dict = {}
    while True:
        try:
            status_response = await client.check_request_status(rindex)
        except GDEXAuthError as e:
            # Auth doesn't recover mid-poll — stop instead of retrying for timeout_s.
            return _json({"outcome": "error", "rindex": rindex, "error": str(e), "error_type": "GDEXAuthError"})
        except GDEXError as e:
            return _json(
                {"outcome": "error", "rindex": rindex, "error": str(e), "error_type": type(e).__name__}
            )

        outcome = _classify_status(status_response)
        if outcome in ("ok", "failed"):
            result = {"outcome": outcome, "rindex": rindex, "status": status_response}
            if outcome == "ok":
                result["files"] = await _safe(client.get_request_files(rindex))
            return _json(result)

        if time.monotonic() >= deadline:
            return _json(
                {
                    "outcome": "timeout",
                    "rindex": rindex,
                    "status": status_response,
                    "note": f"Still not finished after {timeout_s}s. Call "
                    f"check_request_status('{rindex}') to keep checking.",
                }
            )
        await asyncio.sleep(poll_interval_s)


@mcp.tool()
async def purge_request(rindex: str) -> str:
    """Delete a subsetting request and its output files. Requires GDEX_TOKEN.

    Args:
        rindex: Request index/ID to purge
    """
    data = await client.purge_request(rindex)
    return _json(data)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
#
# These seed a conversation with a concrete plan rather than fetching data
# themselves — that keeps them thin (no new failure surface) and leaves tool
# selection/sequencing to the model, consistent with how the rest of this
# server treats tools as the single source of truth for GDEX calls.


@mcp.prompt()
def find_and_describe_dataset(topic: str) -> str:
    """Search GDEX for datasets on a topic and summarize the best match."""
    return (
        f'Find GDEX datasets about "{topic}" and describe the best match.\n\n'
        f'1. Call list_datasets(query="{topic}") to find candidate dataset IDs.\n'
        "2. If there are multiple plausible matches, briefly list them (id + title) "
        "and pick the most relevant one for the topic — or ask the user to choose "
        "if it's genuinely ambiguous.\n"
        "3. Call describe_dataset on the chosen dsid for its abstract, temporal/spatial "
        "coverage, variables, data formats, and volume.\n"
        "4. Summarize it for the user: what it contains, its time/space coverage, and "
        "roughly how large it is. Mention get_data_access or has_arco as next steps if "
        "the user wants to actually pull data — and if the goal is analysis rather than "
        "a raw file, check for a Kerchunk Reference Files group (get_file_groups) or ARCO "
        "variables first, since those avoid downloading whole files just to subset them."
    )


@mcp.prompt()
def prepare_subset_request(dsid: str, goal: str = "") -> str:
    """Walk through building, validating, and submitting a subset request for a dataset."""
    goal_line = f"\nThe user wants: {goal}\n" if goal else ""
    return (
        f"Prepare a subsetting request for dataset {dsid}.{goal_line}\n"
        f"1. Call get_control_file_template(dsid=\"{dsid}\") to see the fields this "
        "dataset's requests accept.\n"
        "2. Draft a request body (as a JSON object) covering the fields relevant to "
        "the user's goal — check get_dataset_temporal/get_dataset_spatial_coverage/"
        "get_dataset_variables first if you need to confirm valid ranges or names.\n"
        f'3. Call validate_subset_request(dsid="{dsid}", request_json=<your draft>) and '
        "fix anything it flags before moving on.\n"
        "4. Confirm the request with the user (it may take a while to run and consume "
        "their quota), then call submit_and_wait_for_request to submit it and wait for "
        "completion — or submit_subset_request alone if they'd rather check back later "
        "with check_request_status.\n"
        "5. Once it completes, call get_request_files to hand back the output file list."
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    mcp.run()


if __name__ == "__main__":
    main()
