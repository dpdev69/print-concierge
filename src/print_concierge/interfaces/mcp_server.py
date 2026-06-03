from __future__ import annotations

from typing import Any, Mapping

from print_concierge import planner as print_planner
from print_concierge.planner import PrintPlan
from print_concierge.search.base import ModelSearchResult
from print_concierge.search.local_archive import LocalArchiveSearchProvider


def list_printers(*, client: Any = None) -> list[dict[str, Any]]:
    return list(client.list_printers()) if client else []


def get_printer_status(printer_id: str, *, client: Any = None) -> dict[str, Any]:
    if client:
        return dict(client.get_printer_status(printer_id))
    return {"id": printer_id, "status": "unknown"}


def search_archive_or_models(
    query: str,
    *,
    archive_provider: Any = None,
    search_provider: Any = None,
) -> list[dict[str, Any]]:
    provider = archive_provider or search_provider or LocalArchiveSearchProvider()
    return [_jsonable(result) for result in provider.search(query)]


def prepare_print_plan(
    *,
    selected: ModelSearchResult | Mapping[str, Any],
    printer: Mapping[str, Any],
    material: Mapping[str, Any],
    profile: Mapping[str, Any],
    user_id: str,
    session_id: str,
    file_bytes: bytes | None = None,
    file_path: str | None = None,
    confirmation_service: Any = None,
    print_client: Any = None,
) -> dict[str, Any]:
    plan = print_planner.prepare_print_plan(
        selected=selected,
        printer=printer,
        material=material,
        profile=profile,
        user_id=user_id,
        session_id=session_id,
        file_bytes=file_bytes,
        file_path=file_path,
        confirmation_service=confirmation_service,
        print_client=print_client,
    )
    return _jsonable(plan)


def show_print_plan(plan: PrintPlan | Mapping[str, Any]) -> dict[str, Any]:
    return _jsonable(plan)


def request_confirmation(plan: PrintPlan | Mapping[str, Any], *, confirmation_service: Any) -> dict[str, Any]:
    payload = _jsonable(plan)
    plan_id = payload.get("job_id") or payload.get("plan_id")
    session_id = str(
        payload.get("session_id")
        or payload.get("slicer_settings", {}).get("session_id")
        or payload["user_id"]
    )
    if not payload.get("plan_hash"):
        raise ValueError("plan_hash is required to request confirmation")
    if not payload.get("session_id") and not payload.get("slicer_settings", {}).get("session_id"):
        raise ValueError("session_id is required to request confirmation")
    if hasattr(confirmation_service, "request_confirmation"):
        result = confirmation_service.request_confirmation(payload)
    elif hasattr(confirmation_service, "create_challenge"):
        result = confirmation_service.create_challenge(
            user_id=str(payload["user_id"]),
            chat_id=session_id,
            job_id=str(plan_id),
            file_hash=str(payload["file_hash"]),
            printer_id=str(payload["printer"]["printer_id"]),
            material_profile=str(payload["material_profile"]),
            plan_hash=str(payload["plan_hash"]),
        )
    else:
        raise TypeError("confirmation_service must expose request_confirmation or create_challenge")
    return _jsonable(result)


def queue_confirmed_print(confirmation_token: str, *, client: Any) -> dict[str, Any]:
    if hasattr(client, "queue_confirmed_print"):
        result = dict(client.queue_confirmed_print(confirmation_token))
        if not result.get("job_id"):
            raise ValueError("queue_confirmed_print response must include job_id")
        return result
    raise TypeError("queue_confirmed_print requires a confirmation-aware queue gateway")


def get_job_status(job_id: str, *, client: Any = None) -> dict[str, Any]:
    if client:
        return dict(client.get_job_status(job_id))
    return {"job_id": job_id, "status": "unknown"}


def main() -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "The MCP SDK is not installed. Install with `uv sync --extra mcp`, "
            "or import print_concierge.interfaces.mcp_server and call the tool functions directly."
        ) from exc

    server = FastMCP("print-concierge")
    server.tool()(list_printers)
    server.tool()(get_printer_status)
    server.tool()(search_archive_or_models)
    server.tool()(prepare_print_plan)
    server.tool()(show_print_plan)
    server.tool()(request_confirmation)
    server.tool()(queue_confirmed_print)
    server.tool()(get_job_status)
    server.run()


def _jsonable(value: Any) -> Any:
    if isinstance(value, PrintPlan):
        payload = value.to_dict()
        payload["plan_hash"] = value.plan_hash
        session_id = payload.get("slicer_settings", {}).get("session_id")
        if session_id is not None:
            payload["session_id"] = session_id
        return payload
    if isinstance(value, ModelSearchResult):
        return value.to_dict()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dict__") and value.__class__.__module__.startswith("print_concierge."):
        return {key: _jsonable(item) for key, item in value.__dict__.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value
