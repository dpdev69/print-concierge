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
    _SENSITIVE_RESPONSE_KEYS = {
        "access_code",
        "accesscode",
        "api_key",
        "apikey",
        "password",
        "secret",
        "serial_number",
        "serialnumber",
        "token",
    }
    _ALLOWED_METHOD_PATHS = {
        ("GET", "/api/v1/printers/"),
        ("GET", "/api/v1/archives/"),
        ("GET", "/api/v1/queue/"),
        ("POST", "/api/v1/queue/"),
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
        return self._request("GET", "/api/v1/printers/")

    def get_printer(self, printer_id: str) -> Any:
        return self._request("GET", f"/api/v1/printers/{self._path_id(printer_id)}")

    def get_printer_status(self, printer_id: str) -> Any:
        return self._request(
            "GET", f"/api/v1/printers/{self._path_id(printer_id)}/status"
        )

    def list_archives(self) -> Any:
        return self._request("GET", "/api/v1/archives/")

    def get_archive(self, archive_id: str) -> Any:
        return self._request("GET", f"/api/v1/archives/{self._path_id(archive_id)}")

    def get_snapshot(self, printer_id: str) -> Any:
        return self._request(
            "GET", f"/api/v1/printers/{self._path_id(printer_id)}/camera/snapshot"
        )

    def list_queue(self) -> Any:
        return self._request("GET", "/api/v1/queue/")

    def get_queue_item(self, item_id: str) -> Any:
        return self._request("GET", f"/api/v1/queue/{self._path_id(item_id)}")

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        item_id = str(job_id).removeprefix("queue-")
        item = self.get_queue_item(item_id)
        return {
            "job_id": str(item.get("id", item_id)) if isinstance(item, dict) else item_id,
            "status": str(item.get("status", "unknown")) if isinstance(item, dict) else "unknown",
            "queue_item": item,
        }

    def queue_print(self, plan: dict[str, Any]) -> Any:
        if plan.get("_print_concierge_confirmed") is not True:
            raise BambuddyError("queue_print requires a confirmed Print Concierge gateway payload.")
        result = self._request("POST", "/api/v1/queue/", json=self._queue_payload(plan))
        if not isinstance(result, dict):
            raise BambuddyAmbiguousActionError(
                "Queue response did not include a job id; print state is ambiguous."
            )
        queue_id = result.get("job_id") or result.get("id")
        if not queue_id:
            raise BambuddyAmbiguousActionError(
                "Queue response did not include a job id; print state is ambiguous."
            )
        return {
            "job_id": str(queue_id),
            "status": result.get("status", "queued"),
            "queue_item": result,
        }

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
        return self._redact_response(response.json())

    @classmethod
    def _validate_allowed_path(cls, method: str, path: str) -> None:
        if (method, path) in cls._ALLOWED_METHOD_PATHS:
            return
        parts = path.strip("/").split("/")
        if method == "GET" and len(parts) == 4 and parts[:3] == ["api", "v1", "printers"]:
            return
        if (
            method == "GET"
            and len(parts) == 5
            and parts[:3] == ["api", "v1", "printers"]
            and parts[4] == "status"
        ):
            return
        if (
            method == "GET"
            and len(parts) == 6
            and parts[:3] == ["api", "v1", "printers"]
            and parts[4:] == ["camera", "snapshot"]
        ):
            return
        if method == "GET" and len(parts) == 4 and parts[:3] == ["api", "v1", "archives"]:
            return
        if method == "GET" and len(parts) == 4 and parts[:3] == ["api", "v1", "queue"]:
            return
        raise BambuddyError(f"Endpoint is not allowlisted: {method} {path}")

    @staticmethod
    def _path_id(value: str) -> str:
        return quote(str(value), safe="")

    @classmethod
    def _queue_payload(cls, plan: dict[str, Any]) -> dict[str, Any]:
        metadata = plan.get("model", {}).get("metadata", {})
        archive_id = metadata.get("archive_id") or plan.get("archive_id")
        if archive_id is None:
            raise BambuddyError("confirmed queue payload requires a Bambuddy archive_id")
        printer_id = plan.get("printer", {}).get("printer_id") or plan.get("printer_id")
        if printer_id is None:
            raise BambuddyError("confirmed queue payload requires a printer_id")
        material = str(plan.get("material_profile", "")).split("/", 1)[0].strip()
        payload = {
            "archive_id": int(archive_id),
            "bed_levelling": True,
            "flow_cali": False,
            "gcode_injection": False,
            "layer_inspect": False,
            "manual_start": cls._manual_start_enabled(),
            "printer_id": int(printer_id),
            "quantity": 1,
            "timelapse": False,
            "use_ams": True,
            "vibration_cali": True,
        }
        if material:
            payload["required_filament_types"] = [material]
        return payload

    @staticmethod
    def _manual_start_enabled() -> bool:
        value = os.environ.get("PRINT_CONCIERGE_BAMBUDDY_MANUAL_START", "true").lower()
        return value not in {"0", "false", "no", "off"}

    @classmethod
    def _redact_response(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [cls._redact_response(item) for item in value]
        if isinstance(value, dict):
            return {
                key: "<redacted>"
                if str(key).lower() in cls._SENSITIVE_RESPONSE_KEYS
                else cls._redact_response(item)
                for key, item in value.items()
            }
        return value
