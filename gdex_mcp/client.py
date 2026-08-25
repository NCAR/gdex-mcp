"""HTTP client wrapping the GDEX REST API."""

import httpx


class GDEXError(RuntimeError):
    """Base class for errors reported by the GDEX API — either a non-2xx HTTP
    response, or a `{"status": "error"}` envelope on an otherwise-200 response.

    Callers that just want a message can keep catching this (or plain
    Exception); callers that want to react differently to "you're not logged
    in" vs. "that dataset doesn't exist" can catch the subclasses below.
    """


class GDEXAuthError(GDEXError):
    """Missing, invalid, or expired GDEX_TOKEN (HTTP 401/403, or an error
    envelope whose message reads like an auth failure)."""


class GDEXNotFoundError(GDEXError):
    """The dataset, request, or other resource ID wasn't recognized by GDEX
    (HTTP 404, or an error envelope whose message reads like "not found")."""


class GDEXValidationError(GDEXError):
    """GDEX rejected the request body/parameters as invalid (HTTP 400/422)."""


# Keyword sniffing used only for the JSON-envelope error case, where GDEX
# reports `{"status": "error"}` on an HTTP 200 and the only signal we have is
# the message text. HTTP-status-code classification (below) is authoritative;
# this is a best-effort fallback — if GDEX's actual wording drifts from this,
# affected errors just fall through to the generic GDEXError, never misfire
# as the wrong subclass silently.
_AUTH_HINTS = ("token", "auth", "unauthorized", "permission", "forbidden", "credential")
_NOT_FOUND_HINTS = ("not found", "does not exist", "no such", "unknown dataset", "unknown request")


def _classify_message(message: str) -> type[GDEXError]:
    m = message.lower()
    if any(h in m for h in _AUTH_HINTS):
        return GDEXAuthError
    if any(h in m for h in _NOT_FOUND_HINTS):
        return GDEXNotFoundError
    return GDEXError


class GDEXClient:
    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        return headers

    def _unwrap(self, data: dict) -> dict:
        if data.get("status") == "error":
            msgs = data.get("error_messages") or ["Unknown error"]
            message = "; ".join(msgs)
            raise _classify_message(message)(message)
        return data.get("data", data)

    def _error_from_response(self, r: httpx.Response) -> GDEXError:
        """Build a classified GDEXError from a non-2xx response. The HTTP
        status code is the authoritative signal here (unlike `_unwrap`'s
        keyword sniffing) since GDEX's schema doesn't document error bodies."""
        message = f"GDEX API returned HTTP {r.status_code} for {r.request.url}"
        try:
            body = r.json()
            if isinstance(body, dict):
                msgs = body.get("error_messages")
                if msgs:
                    message = "; ".join(msgs)
                elif body.get("detail"):
                    message = str(body["detail"])
        except ValueError:
            pass  # non-JSON error body (HTML error page, etc.) — keep the generic message

        if r.status_code in (401, 403):
            return GDEXAuthError(f"GDEX authentication error: {message}")
        if r.status_code == 404:
            return GDEXNotFoundError(f"GDEX resource not found: {message}")
        if r.status_code in (400, 422):
            return GDEXValidationError(f"GDEX rejected the request: {message}")
        return GDEXError(message)

    async def _request(
        self, method: str, path: str, *, params: dict | None = None, json_body: dict | None = None
    ) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.request(
                method,
                f"{self.base_url}{path}",
                headers=self._headers(),
                params=params,
                json=json_body,
                timeout=30,
            )
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise self._error_from_response(r) from e
            return self._unwrap(r.json())

    async def _get(self, path: str, **params) -> dict:
        return await self._request(
            "GET", path, params={k: v for k, v in params.items() if v is not None}
        )

    async def _post(self, path: str, body: dict) -> dict:
        return await self._request("POST", path, json_body=body)

    async def _delete(self, path: str) -> dict:
        return await self._request("DELETE", path)

    # --- Dataset listing ---

    async def list_datasets(self) -> dict:
        return await self._get("/api/get_datasets/")

    # --- Dataset metadata ---

    async def get_metadata(self, dsid: str) -> dict:
        return await self._get(f"/api/metadata/{dsid}/")

    async def get_abstract(self, dsid: str) -> dict:
        return await self._get(f"/api/datasets/{dsid}/abstract/")

    async def get_variables(self, dsid: str) -> dict:
        return await self._get(f"/api/datasets/{dsid}/variables/")

    async def get_temporal(self, dsid: str) -> dict:
        return await self._get(f"/api/datasets/{dsid}/temporal/")

    async def get_spatial_coverage(self, dsid: str) -> dict:
        return await self._get(f"/api/datasets/{dsid}/spatial_coverage/")

    async def get_publications(self, dsid: str) -> dict:
        return await self._get(f"/api/datasets/{dsid}/publications/")

    async def get_contributors(self, dsid: str) -> dict:
        return await self._get(f"/api/datasets/{dsid}/contributors/")

    async def get_data_formats(self, dsid: str) -> dict:
        return await self._get(f"/api/datasets/{dsid}/data_formats/")

    async def get_data_types(self, dsid: str) -> dict:
        return await self._get(f"/api/datasets/{dsid}/data_types/")

    async def get_volume(self, dsid: str) -> dict:
        return await self._get(f"/api/datasets/{dsid}/volume/")

    async def get_related_datasets(self, dsid: str) -> dict:
        return await self._get(f"/api/datasets/{dsid}/related_datasets/")

    async def get_documentation(self, dsid: str) -> dict:
        return await self._get(f"/api/datasets/{dsid}/documentation/")

    # --- Files ---

    async def get_file_groups(self, dsid: str, gindex: str | None = None) -> dict:
        if gindex:
            return await self._get(f"/api/datasets/{dsid}/groups/{gindex}/")
        return await self._get(f"/api/datasets/{dsid}/groups/")

    async def get_dataset_files(
        self,
        dsid: str,
        gindex: str | None = None,
        page: int | None = None,
        filter_wfile: str | None = None,
        fl: str | None = None,
    ) -> dict:
        path = f"/api/datasets/{dsid}/filelist/{gindex}/" if gindex else f"/api/datasets/{dsid}/filelist/"
        return await self._get(path, page=page, filter_wfile=filter_wfile, fl=fl)

    # --- File search ---
    #
    # A separate, more targeted way to find data files than get_dataset_files:
    # search by content (grid parameters, cyclone-fix storm data, sensor
    # observations) rather than by file-group browsing. Each dataset supports
    # a subset of the three datatypes below — call get_filesearch_datatypes
    # first to see which. The filters/* endpoints report valid codes to pass
    # to the matching files/* endpoint; both files/* and filters/grid/ take
    # the same filter arguments. files/* responses are paginated and carry a
    # result_id for get_filesearch_result_page to page through.

    async def get_filesearch_datatypes(self, dsid: str) -> dict:
        return await self._get(f"/api/datasets/{dsid}/filesearch/datatypes/")

    async def get_filesearch_cyclone_fix_filters(
        self,
        dsid: str,
        valid_datetime_min: str | None = None,
        valid_datetime_max: str | None = None,
    ) -> dict:
        return await self._get(
            f"/api/datasets/{dsid}/filesearch/filters/cyclone_fix/",
            valid_datetime_min=valid_datetime_min,
            valid_datetime_max=valid_datetime_max,
        )

    async def get_filesearch_grid_filters(
        self,
        dsid: str,
        valid_datetime_min: str | None = None,
        valid_datetime_max: str | None = None,
        parameters: list[str] | None = None,
        products: list[str] | None = None,
        grids: list[str] | None = None,
        levels: list[str] | None = None,
    ) -> dict:
        return await self._get(
            f"/api/datasets/{dsid}/filesearch/filters/grid/",
            valid_datetime_min=valid_datetime_min,
            valid_datetime_max=valid_datetime_max,
            parameters=parameters,
            products=products,
            grids=grids,
            levels=levels,
        )

    async def get_filesearch_sensor_filters(
        self,
        dsid: str,
        valid_date_min: str | None = None,
        valid_date_max: str | None = None,
    ) -> dict:
        return await self._get(
            f"/api/datasets/{dsid}/filesearch/filters/sensor/",
            valid_date_min=valid_date_min,
            valid_date_max=valid_date_max,
        )

    async def get_filesearch_cyclone_fix_files(
        self,
        dsid: str,
        valid_datetime_min: str | None = None,
        valid_datetime_max: str | None = None,
    ) -> dict:
        return await self._get(
            f"/api/datasets/{dsid}/filesearch/files/cyclone_fix/",
            valid_datetime_min=valid_datetime_min,
            valid_datetime_max=valid_datetime_max,
        )

    async def get_filesearch_grid_files(
        self,
        dsid: str,
        parameters: list[str],
        valid_datetime_min: str | None = None,
        valid_datetime_max: str | None = None,
        products: list[str] | None = None,
        grids: list[str] | None = None,
        levels: list[str] | None = None,
    ) -> dict:
        # `parameters` is required by this endpoint (unlike filters/grid/, where
        # it's just another optional filter) — GDEX rejects a grid file search
        # with no parameter code to search for.
        return await self._get(
            f"/api/datasets/{dsid}/filesearch/files/grid/",
            parameters=parameters,
            valid_datetime_min=valid_datetime_min,
            valid_datetime_max=valid_datetime_max,
            products=products,
            grids=grids,
            levels=levels,
        )

    async def get_filesearch_sensor_files(
        self,
        dsid: str,
        valid_date_min: str | None = None,
        valid_date_max: str | None = None,
    ) -> dict:
        return await self._get(
            f"/api/datasets/{dsid}/filesearch/files/sensor/",
            valid_date_min=valid_date_min,
            valid_date_max=valid_date_max,
        )

    async def get_filesearch_result_page(self, dsid: str, result_id: str, page_num: int) -> dict:
        return await self._get(f"/api/datasets/{dsid}/filesearch/results/{result_id}/{page_num}/")

    # --- Data access ---

    async def get_data_access(self, dsid: str) -> dict:
        return await self._get(f"/api/datasets/{dsid}/data_access/root")

    # --- ARCO ---

    async def has_arco(self, dsid: str) -> dict:
        return await self._get(f"/api/has_arco/{dsid}/")

    async def get_arco_variables(self, dsid: str) -> dict:
        return await self._get(f"/api/arco_vars/{dsid}/")

    async def search_arco_variables(self, dsid: str, query: str) -> dict:
        return await self._get(f"/api/search_arco_vars/{dsid}/{query}")

    # --- Metrics ---

    async def get_portal_metric(self, metric: str) -> dict:
        return await self._get(f"/api/metrics/{metric}/")

    async def get_dataset_metric(self, dsid: str, metric: str) -> dict:
        return await self._get(f"/api/metrics/dataset/{dsid}/{metric}/")

    # --- Staff ---

    async def get_staff(self, dsid: str | None = None) -> dict:
        if dsid:
            return await self._get(f"/api/get_staff/{dsid}/")
        return await self._get("/api/get_staff/")

    # --- Authenticated: subsetting requests ---

    async def check_request_status(self, rindex: str) -> dict:
        return await self._get(f"/api/status/{rindex}/")

    async def list_request_statuses(self) -> dict:
        return await self._get("/api/status/")

    async def get_request_files(self, rindex: str) -> dict:
        return await self._get(f"/api/get_req_files/{rindex}/")

    async def submit_subset_request(self, request_body: dict) -> dict:
        return await self._post("/api/submit_json/", request_body)

    async def purge_request(self, rindex: str) -> dict:
        return await self._delete(f"/api/purge/{rindex}/")

    async def get_control_file_template(self, dsid: str) -> dict:
        return await self._get(f"/api/control_file_template/{dsid}/")
