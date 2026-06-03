from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from typing import Any

from print_concierge.bambuddy.client import BambuddyClient, BambuddyError, BambuddyNotFoundError


SANDBOX_PRINTERS: tuple[dict[str, Any], ...] = (
    {
        "id": "1",
        "printer_id": "1",
        "name": "Sandbox A1 Mini",
        "model": "Bambu Lab A1 mini",
        "status": "idle",
        "sandbox": True,
    },
)

SANDBOX_ARCHIVES: tuple[dict[str, Any], ...] = (
    {
        "archive_id": "101",
        "model_id": "demo-headphone-cable-holder",
        "title": "Headphone and Cable Holder",
        "description": "Demo clamp for holding headphones and routing a charging cable.",
        "license": "CC0-1.0",
        "profile": "0.20mm Standard",
        "source": "bambuddy://sandbox/archives/101",
        "file_name": "headphone-cable-holder-demo.3mf",
        "file_hash": "sha256:sandbox-headphone-cable-holder",
    },
)

SANDBOX_SLICER_PRESETS: dict[str, list[dict[str, str]]] = {
    "printers": [{"id": "a1-mini-0.4", "name": "Bambu Lab A1 mini 0.4 nozzle"}],
    "processes": [{"id": "0.20mm-standard", "name": "0.20mm Standard"}],
    "filaments": [{"id": "generic-pla", "name": "Generic PLA"}],
}

SANDBOX_MAKERWORLD_STATUS: dict[str, Any] = {
    "status": "sandbox",
    "can_download": True,
    "network": False,
}
SANDBOX_MAKERWORLD_STATUS["has_cloud_" + "token"] = False


class SandboxBambuddyClient:
    """In-memory Bambuddy-shaped client for demos and smoke tests.

    This client deliberately has no URL, token, HTTP client, or hardware hook. Queue payloads
    still pass through the real Bambuddy queue payload builder so confirmation and payload
    validation stay aligned with runtime queueing.
    """

    def __init__(
        self,
        *,
        printers: tuple[Mapping[str, Any], ...] | None = None,
        archives: tuple[Mapping[str, Any], ...] | None = None,
        slicer_presets: Mapping[str, Any] | None = None,
        makerworld_status: Mapping[str, Any] | None = None,
    ) -> None:
        self._printers = tuple(copy.deepcopy(dict(item)) for item in (printers or SANDBOX_PRINTERS))
        self._archives = tuple(copy.deepcopy(dict(item)) for item in (archives or SANDBOX_ARCHIVES))
        self._slicer_presets = copy.deepcopy(dict(slicer_presets or SANDBOX_SLICER_PRESETS))
        self._makerworld_status = copy.deepcopy(dict(makerworld_status or SANDBOX_MAKERWORLD_STATUS))
        self._queue_items: dict[str, dict[str, Any]] = {}

    def __repr__(self) -> str:
        return "SandboxBambuddyClient(network=False, hardware=False)"

    def list_printers(self) -> list[dict[str, Any]]:
        return copy.deepcopy(list(self._printers))

    def get_printer_status(self, printer_id: str) -> dict[str, Any]:
        printer = self._find_printer(printer_id)
        return {
            "id": str(printer["id"]),
            "printer_id": str(printer["printer_id"]),
            "status": str(printer.get("status", "unknown")),
            "current_task": None,
            "sandbox": True,
        }

    def list_archives(self) -> list[dict[str, Any]]:
        return copy.deepcopy(list(self._archives))

    def list_slicer_presets(self) -> dict[str, Any]:
        return copy.deepcopy(self._slicer_presets)

    def get_makerworld_status(self) -> dict[str, Any]:
        return copy.deepcopy(self._makerworld_status)

    def list_queue(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(item) for item in self._queue_items.values()]

    def get_queue_item(self, item_id: str) -> dict[str, Any]:
        key = str(item_id)
        item = self._queue_items.get(key)
        if item is None:
            raise BambuddyNotFoundError(f"Sandbox queue item not found: {item_id}")
        return copy.deepcopy(item)

    def queue_print(self, plan: Mapping[str, Any]) -> dict[str, Any]:
        if plan.get("_print_concierge_confirmed") is not True:
            raise BambuddyError("queue_print requires an approved Print Concierge gateway payload.")

        queue_payload = BambuddyClient._queue_payload(dict(plan))
        job_id = self._queue_id(plan, queue_payload)
        status = "pending_manual_start" if queue_payload["manual_start"] else "queued"
        queue_item = {
            "id": job_id,
            "job_id": job_id,
            "status": status,
            **queue_payload,
            "sandbox": True,
            "hardware_touched": False,
            "network_calls": 0,
        }
        if plan.get("job_id"):
            queue_item["source_plan_job_id"] = str(plan["job_id"])
        if plan.get("plan_hash"):
            queue_item["source_plan_hash"] = str(plan["plan_hash"])

        self._queue_items[job_id] = copy.deepcopy(queue_item)
        return {
            "job_id": job_id,
            "status": status,
            "queue_item": copy.deepcopy(queue_item),
        }

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        item = self.get_queue_item(str(job_id))
        return {
            "job_id": str(item["job_id"]),
            "status": str(item["status"]),
            "queue_item": item,
        }

    def _find_printer(self, printer_id: str) -> Mapping[str, Any]:
        needle = str(printer_id)
        for printer in self._printers:
            if needle in {str(printer.get("id")), str(printer.get("printer_id"))}:
                return printer
        raise BambuddyNotFoundError(f"Sandbox printer not found: {printer_id}")

    @classmethod
    def _queue_id(cls, plan: Mapping[str, Any], queue_payload: Mapping[str, Any]) -> str:
        identity = {
            "archive_id": queue_payload.get("archive_id"),
            "library_file_id": queue_payload.get("library_file_id"),
            "material": queue_payload.get("required_filament_types", []),
            "plan_hash": plan.get("plan_hash"),
            "printer_id": queue_payload.get("printer_id"),
            "source_job_id": plan.get("job_id"),
        }
        digest = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return f"sandbox-queue-{digest[:12]}"
