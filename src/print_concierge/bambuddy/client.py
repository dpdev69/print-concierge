from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import httpx


class BambuddyError(Exception):
    pass


class BambuddyNotFoundError(BambuddyError):
    pass


class BambuddyConnectionError(BambuddyError):
    pass


class BambuddyAmbiguousActionError(BambuddyError):
    pass


class BambuddyClient:
    _ALLOWED_METHOD_PATHS = {
        ("GET", "/api/printers"),
        ("GET", "/api/archives"),
        ("POST", "/api/queue"),
    }

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        http_client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("BAMBUDDY_BASE_URL") or "").rstrip(
            "/"
        )
        self._api_key = api_key or os.environ.get("BAMBUDDY_API_KEY") or ""
        if not self.base_url:
            raise BambuddyError("Bambuddy base URL is required.")
        if not self._api_key:
            raise BambuddyError("Bambuddy API key is required.")
        self._client = http_client or httpx.Client(timeout=timeout)

    def __repr__(self) -> str:
        return f"BambuddyClient(base_url={self.base_url!r}, api_key=<redacted>)"

    def list_printers(self) -> Any:
        return self._request("GET", "/api/printers")

    def get_printer(self, printer_id: str) -> Any:
        return self._request("GET", f"/api/printers/{self._path_id(printer_id)}")

    def get_printer_status(self, printer_id: str) -> Any:
        return self._request(
            "GET", f"/api/printers/{self._path_id(printer_id)}/status"
        )

    def list_archives(self) -> Any:
        return self._request("GET", "/api/archives")

    def get_archive(self, archive_id: str) -> Any:
        return self._request("GET", f"/api/archives/{self._path_id(archive_id)}")

    def get_snapshot(self, printer_id: str) -> Any:
        return self._request(
            "GET", f"/api/printers/{self._path_id(printer_id)}/snapshot"
        )

    def queue_print(self, plan: dict[str, Any]) -> Any:
        if plan.get("_print_concierge_confirmed") is not True:
            raise BambuddyError("queue_print requires a confirmed Print Concierge gateway payload.")
        result = self._request("POST", "/api/queue", json=plan)
        if not isinstance(result, dict) or not result.get("job_id"):
            raise BambuddyAmbiguousActionError(
                "Queue response did not include a job id; print state is ambiguous."
            )
        return result

    def _request(
        self, method: str, path: str, *, json: dict[str, Any] | None = None
    ) -> Any:
        method = method.upper()
        self._validate_allowed_path(method, path)
        url = f"{self.base_url}{path}"
        headers = {"X-API-Key": self._api_key}
        try:
            response = self._client.request(method, url, headers=headers, json=json)
        except httpx.HTTPError as exc:
            raise BambuddyConnectionError(
                f"Bambuddy request failed: {exc.__class__.__name__}"
            ) from exc

        if response.status_code == 404:
            raise BambuddyNotFoundError(f"Bambuddy resource not found: {path}")
        if response.status_code >= 400:
            raise BambuddyError(
                f"Bambuddy request failed with status {response.status_code}: {path}"
            )
        if not response.content:
            return None
        return response.json()

    @classmethod
    def _validate_allowed_path(cls, method: str, path: str) -> None:
        if (method, path) in cls._ALLOWED_METHOD_PATHS:
            return
        parts = path.strip("/").split("/")
        if method == "GET" and len(parts) == 3 and parts[:2] == ["api", "printers"]:
            return
        if (
            method == "GET"
            and len(parts) == 4
            and parts[:2] == ["api", "printers"]
            and parts[3] in {"status", "snapshot"}
        ):
            return
        if method == "GET" and len(parts) == 3 and parts[:2] == ["api", "archives"]:
            return
        raise BambuddyError(f"Endpoint is not allowlisted: {method} {path}")

    @staticmethod
    def _path_id(value: str) -> str:
        return quote(str(value), safe="")
