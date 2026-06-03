from __future__ import annotations

from typing import Any, Mapping

from print_concierge import planner as print_planner
from print_concierge.bambuddy import BambuddyClient, BambuddyError
from print_concierge.planner import PrintPlan
from print_concierge.public_imports import import_public_candidate as import_public_model_candidate
from print_concierge.runtime import RuntimeApprovalService, RuntimeState
from print_concierge.search.base import ModelSearchResult
from print_concierge.search.composite import CompositeSearchProvider
from print_concierge.search.external import (
    configured_external_providers,
    default_public_search_provider,
)
from print_concierge.search.local_archive import LocalArchiveSearchProvider


def list_printers(*, client: Any = None) -> list[dict[str, Any]]:
    return list(client.list_printers()) if client else []


def get_printer_status(printer_id: str, *, client: Any = None) -> dict[str, Any]:
    if client:
        return dict(client.get_printer_status(printer_id))
    return {"id": printer_id, "status": "unknown"}


def list_slicer_presets(*, client: Any = None) -> dict[str, Any]:
    if client and hasattr(client, "list_slicer_presets"):
        return dict(client.list_slicer_presets())
    return {"printers": [], "processes": [], "filaments": []}


def search_archive_or_models(
    query: str,
    *,
    limit: int | None = None,
    archive_provider: Any = None,
    search_provider: Any = None,
) -> list[dict[str, Any]]:
    provider = archive_provider or search_provider or _default_search_provider()
    return [_jsonable(result) for result in _search_provider(provider, query, limit=limit)]


def import_public_candidate(
    selected: ModelSearchResult | Mapping[str, Any],
    *,
    profile_id: int | None = None,
    folder_id: int | None = None,
    slice_options: Mapping[str, Any] | None = None,
    slice_wait_seconds: float | None = None,
    client: Any = None,
) -> dict[str, Any]:
    imported = import_public_model_candidate(
        selected,
        client=client or _default_bambuddy_client(),
        profile_id=profile_id,
        folder_id=folder_id,
        slice_options=slice_options,
        slice_wait_seconds=slice_wait_seconds,
    )
    return _jsonable(imported)


def get_public_import_status(*, client: Any = None) -> dict[str, Any]:
    runtime_client = client or _default_bambuddy_client()
    if runtime_client and hasattr(runtime_client, "get_makerworld_status"):
        return {"makerworld": dict(runtime_client.get_makerworld_status())}
    return {"makerworld": {"status": "unavailable", "can_download": False}}


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
    approval_service: Any = None,
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
        approval_service=approval_service,
        print_client=print_client,
    )
    return _jsonable(plan)


def show_print_plan(plan: PrintPlan | Mapping[str, Any]) -> dict[str, Any]:
    return _jsonable(plan)


def create_print_request(
    plan: PrintPlan | Mapping[str, Any], *, approval_service: Any = None
) -> dict[str, Any]:
    payload = _jsonable(plan)
    if not payload.get("plan_hash"):
        raise ValueError("plan_hash is required to create a print request")
    if not payload.get("session_id") and not payload.get("slicer_settings", {}).get("session_id"):
        raise ValueError("session_id is required to create a print request")
    service = approval_service or _default_approval_service()
    if not hasattr(service, "create_print_request"):
        raise TypeError("approval_service must expose create_print_request")
    result = service.create_print_request(payload)
    return _jsonable(result)


def get_print_request_status(
    request_id: str, *, approval_service: Any = None
) -> dict[str, Any]:
    service = approval_service or _default_approval_service()
    if not hasattr(service, "get_print_request_status"):
        raise TypeError("approval_service must expose get_print_request_status")
    return _jsonable(service.get_print_request_status(request_id))


def get_job_status(job_id: str, *, client: Any = None) -> dict[str, Any]:
    if client and hasattr(client, "get_job_status"):
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

    def list_printers() -> list[dict[str, Any]]:
        return globals()["list_printers"](client=_default_bambuddy_client())

    def get_printer_status(printer_id: str) -> dict[str, Any]:
        return globals()["get_printer_status"](printer_id, client=_default_bambuddy_client())

    def list_slicer_presets() -> dict[str, Any]:
        return globals()["list_slicer_presets"](client=_default_bambuddy_client())

    def search_archive_or_models(query: str, limit: int = 5) -> list[dict[str, Any]]:
        return globals()["search_archive_or_models"](query, limit=limit)

    def import_public_candidate(
        selected: dict[str, Any],
        profile_id: int | None = None,
        folder_id: int | None = None,
        slice_options: dict[str, Any] | None = None,
        slice_wait_seconds: float | None = None,
    ) -> dict[str, Any]:
        return globals()["import_public_candidate"](
            selected,
            profile_id=profile_id,
            folder_id=folder_id,
            slice_options=slice_options,
            slice_wait_seconds=slice_wait_seconds,
            client=_default_bambuddy_client(),
        )

    def get_public_import_status() -> dict[str, Any]:
        return globals()["get_public_import_status"](client=_default_bambuddy_client())

    def prepare_print_plan(
        *,
        selected: dict[str, Any],
        printer: dict[str, Any],
        material: dict[str, Any],
        profile: dict[str, Any],
        user_id: str,
        session_id: str,
        file_bytes: bytes | None = None,
        file_path: str | None = None,
    ) -> dict[str, Any]:
        return globals()["prepare_print_plan"](
            selected=selected,
            printer=printer,
            material=material,
            profile=profile,
            user_id=user_id,
            session_id=session_id,
            file_bytes=file_bytes,
            file_path=file_path,
        )

    def show_print_plan(plan: dict[str, Any]) -> dict[str, Any]:
        return globals()["show_print_plan"](plan)

    def create_print_request(plan: dict[str, Any]) -> dict[str, Any]:
        return globals()["create_print_request"](
            plan,
            approval_service=_default_approval_service(),
        )

    def get_print_request_status(request_id: str) -> dict[str, Any]:
        return globals()["get_print_request_status"](
            request_id,
            approval_service=_default_approval_service(),
        )

    def get_job_status(job_id: str) -> dict[str, Any]:
        return globals()["get_job_status"](job_id, client=_default_bambuddy_client())

    for tool in (
        list_printers,
        get_printer_status,
        list_slicer_presets,
        search_archive_or_models,
        import_public_candidate,
        get_public_import_status,
        prepare_print_plan,
        show_print_plan,
        create_print_request,
        get_print_request_status,
        get_job_status,
    ):
        server.tool()(tool)
    server.run()


def _default_bambuddy_client() -> Any:
    try:
        return BambuddyClient()
    except BambuddyError:
        return None


def _default_archive_provider(client: Any = None) -> LocalArchiveSearchProvider:
    client = client if client is not None else _default_bambuddy_client()
    if client is None or not hasattr(client, "list_archives"):
        return LocalArchiveSearchProvider()
    return LocalArchiveSearchProvider(client.list_archives())


def _configured_external_search_providers() -> list[Any]:
    return list(configured_external_providers())


def _default_public_search_provider() -> Any:
    return default_public_search_provider()


def _default_search_provider() -> Any:
    providers = [_default_archive_provider(_default_bambuddy_client())]
    providers.extend(_configured_external_search_providers())
    public_provider = _default_public_search_provider()
    if public_provider is not None:
        providers.append(public_provider)
    return CompositeSearchProvider(providers)


def _search_provider(provider: Any, query: str, *, limit: int | None) -> list[Any]:
    if limit is None:
        return list(provider.search(query))
    try:
        results = provider.search(query, limit=limit)
    except TypeError as exc:
        if "unexpected keyword argument" not in str(exc):
            raise
        results = provider.search(query)
    return list(results)[:limit]


def _default_approval_service() -> Any:
    return RuntimeApprovalService(_default_runtime_state())


def _default_runtime_state() -> RuntimeState:
    return RuntimeState()


def _jsonable(value: Any) -> Any:
    if isinstance(value, PrintPlan):
        payload = value.to_dict()
        payload["plan_hash"] = value.plan_hash
        session_id = payload.get("slicer_settings", {}).get("session_id")
        if session_id is not None:
            payload["session_id"] = session_id
        return payload
    if isinstance(value, ModelSearchResult):
        return value.to_public_dict()
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
