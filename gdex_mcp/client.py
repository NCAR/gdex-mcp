"""HTTP client wrapping the GDEX REST API."""

import httpx


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
            raise RuntimeError("; ".join(msgs))
        return data.get("data", data)

    async def _get(self, path: str, **params) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self.base_url}{path}",
                headers=self._headers(),
                params={k: v for k, v in params.items() if v is not None},
                timeout=30,
            )
            r.raise_for_status()
            return self._unwrap(r.json())

    async def _post(self, path: str, body: dict) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self.base_url}{path}",
                headers=self._headers(),
                json=body,
                timeout=30,
            )
            r.raise_for_status()
            return self._unwrap(r.json())

    async def _delete(self, path: str) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.delete(
                f"{self.base_url}{path}",
                headers=self._headers(),
                timeout=30,
            )
            r.raise_for_status()
            return self._unwrap(r.json())

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

    async def get_dataset_files(self, dsid: str, gindex: str | None = None) -> dict:
        if gindex:
            return await self._get(f"/api/datasets/{dsid}/filelist/{gindex}/")
        return await self._get(f"/api/datasets/{dsid}/filelist/")

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
