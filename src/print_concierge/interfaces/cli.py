from __future__ import annotations

import argparse
import json
import sys
from dataclasses import is_dataclass
from typing import Any, Sequence

from print_concierge.bambuddy import BambuddyClient, BambuddyError
from print_concierge.planner import PrintPlan, prepare_print_plan
from print_concierge.public_imports import import_public_candidate
from print_concierge.runtime import RuntimeApprovalService, RuntimeQueueGateway, RuntimeState
from print_concierge.search.base import ModelSearchResult
from print_concierge.search.composite import CompositeSearchProvider
from print_concierge.search.external import (
    configured_external_providers,
    default_public_search_provider,
)
from print_concierge.search.local_archive import LocalArchiveSearchProvider


def main(
    argv: Sequence[str] | None = None,
    *,
    client: Any = None,
    archive_provider: Any = None,
    search_provider: Any = None,
    approval_service: Any = None,
    output: Any = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    out = output or sys.stdout
    client = client if client is not None else _default_client()
    archive_provider = archive_provider or _default_archive_provider(client)
    search_provider = search_provider or _default_search_provider(archive_provider)
    approval_service = approval_service or RuntimeApprovalService(RuntimeState())

    if args.command == "search":
        _emit(out, search_provider.search(args.query, limit=args.limit))
    elif args.command == "printers":
        _emit(out, client.list_printers() if client else [])
    elif args.command == "status":
        _emit(
            out,
            client.get_printer_status(args.printer_id)
            if client
            else {"id": args.printer_id, "status": "unknown"},
        )
    elif args.command == "slicer-presets":
        _emit(
            out,
            client.list_slicer_presets()
            if client and hasattr(client, "list_slicer_presets")
            else {"printers": [], "processes": [], "filaments": []},
        )
    elif args.command == "archives":
        _emit(
            out,
            archive_provider.list_archives()
            if hasattr(archive_provider, "list_archives")
            else [],
        )
    elif args.command == "prepare":
        selected = archive_provider.select(args.archive_id, args.model_id)
        plan = prepare_print_plan(
            selected=selected,
            printer={
                "id": args.printer_id,
                "name": args.printer_id,
                "model": "unknown",
                "fresh": True,
                "provenance": "cli-demo",
            },
            material={"type": args.material, "fresh": True, "provenance": "cli-demo"},
            profile={"name": args.profile, "fresh": True, "provenance": "cli-demo"},
            user_id=args.user_id,
            session_id=args.session_id,
        )
        _emit(out, plan)
    elif args.command == "prepare-selected":
        selected = json.loads(args.selected_json)
        plan = prepare_print_plan(
            selected=selected,
            printer={
                "id": args.printer_id,
                "name": args.printer_id,
                "model": "unknown",
                "fresh": True,
                "provenance": "cli-demo",
            },
            material={"type": args.material, "fresh": True, "provenance": "cli-demo"},
            profile={"name": args.profile, "fresh": True, "provenance": "cli-demo"},
            user_id=args.user_id,
            session_id=args.session_id,
        )
        _emit(out, plan)
    elif args.command == "import-public":
        selected = json.loads(args.candidate_json)
        slice_options = (
            json.loads(args.slice_options_json) if args.slice_options_json else None
        )
        _emit(
            out,
            import_public_candidate(
                selected,
                client=client,
                profile_id=args.profile_id,
                folder_id=args.folder_id,
                slice_options=slice_options,
                slice_wait_seconds=args.slice_wait_seconds,
            ),
        )
    elif args.command == "import-status":
        if client and hasattr(client, "get_makerworld_status"):
            _emit(out, {"makerworld": client.get_makerworld_status()})
        else:
            _emit(out, {"makerworld": {"status": "unavailable", "can_download": False}})
    elif args.command == "request-print":
        plan = json.loads(args.plan_json)
        _emit(out, approval_service.create_print_request(plan))
    elif args.command == "approvals":
        _handle_approvals(args, out, approval_service=approval_service, client=client)
    else:
        parser.error("unknown command")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="print-concierge")
    subparsers = parser.add_subparsers(dest="command", required=True)
    search = subparsers.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)
    subparsers.add_parser("printers")
    status = subparsers.add_parser("status")
    status.add_argument("printer_id")
    subparsers.add_parser("slicer-presets")
    subparsers.add_parser("archives")
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--archive-id", required=True)
    prepare.add_argument("--model-id")
    prepare.add_argument("--printer-id", required=True)
    prepare.add_argument("--material", required=True)
    prepare.add_argument("--profile", required=True)
    prepare.add_argument("--user-id", default="cli-user")
    prepare.add_argument("--session-id", default="cli-session")
    prepare_selected = subparsers.add_parser("prepare-selected")
    prepare_selected.add_argument("--selected-json", required=True)
    prepare_selected.add_argument("--printer-id", required=True)
    prepare_selected.add_argument("--material", required=True)
    prepare_selected.add_argument("--profile", required=True)
    prepare_selected.add_argument("--user-id", default="cli-user")
    prepare_selected.add_argument("--session-id", default="cli-session")
    import_public = subparsers.add_parser("import-public")
    import_public.add_argument("--candidate-json", required=True)
    import_public.add_argument("--profile-id", type=int)
    import_public.add_argument("--folder-id", type=int)
    import_public.add_argument("--slice-options-json")
    import_public.add_argument("--slice-wait-seconds", type=float)
    subparsers.add_parser("import-status")
    request_print = subparsers.add_parser("request-print")
    request_print.add_argument("--plan-json", required=True)
    approvals = subparsers.add_parser("approvals")
    approval_subparsers = approvals.add_subparsers(dest="approval_command", required=True)
    approvals_list = approval_subparsers.add_parser("list")
    approvals_list.add_argument("--status")
    approvals_list.add_argument("--limit", type=int, default=20)
    approvals_show = approval_subparsers.add_parser("show")
    approvals_show.add_argument("request_id")
    approvals_approve = approval_subparsers.add_parser("approve")
    approvals_approve.add_argument("request_id")
    approvals_approve.add_argument("--queue", action="store_true")
    approvals_reject = approval_subparsers.add_parser("reject")
    approvals_reject.add_argument("request_id")
    return parser


def _handle_approvals(
    args: argparse.Namespace,
    output: Any,
    *,
    approval_service: Any,
    client: Any,
) -> None:
    if args.approval_command == "list":
        _emit(
            output,
            approval_service.list_print_requests(status=args.status, limit=args.limit),
        )
    elif args.approval_command == "show":
        _emit(output, approval_service.get_print_request_status(args.request_id))
    elif args.approval_command == "approve":
        if not args.queue:
            approved = approval_service.approve_print_request(args.request_id)
            _emit(output, approved)
            return
        if client is None:
            raise SystemExit("approvals approve --queue requires a Bambuddy client")
        request = approval_service.get_print_request_status(args.request_id)
        if request["status"] == "pending_user_approval":
            approval_service.approve_print_request(args.request_id)
        elif request["status"] != "approved":
            raise ValueError(f"print request is not approved: {request['status']}")
        queued = RuntimeQueueGateway(RuntimeState(), client).queue_approved_print(
            args.request_id
        )
        _emit(
            output,
            approval_service.get_print_request_status(args.request_id)
            | {"queue_result": queued},
        )
    elif args.approval_command == "reject":
        _emit(output, approval_service.reject_print_request(args.request_id))
    else:
        raise SystemExit("unknown approvals command")


def _default_client() -> Any:
    try:
        return BambuddyClient()
    except BambuddyError:
        return None


def _default_archive_provider(client: Any) -> LocalArchiveSearchProvider:
    if client is None or not hasattr(client, "list_archives"):
        return LocalArchiveSearchProvider()
    return LocalArchiveSearchProvider(client.list_archives())


def _default_search_provider(archive_provider: Any) -> CompositeSearchProvider:
    providers = []
    if hasattr(archive_provider, "search"):
        providers.append(archive_provider)
    providers.extend(configured_external_providers())
    public_provider = default_public_search_provider()
    if public_provider is not None:
        providers.append(public_provider)
    return CompositeSearchProvider(providers)


def _emit(output: Any, payload: Any) -> None:
    output.write(json.dumps(_jsonable(payload), sort_keys=True) + "\n")


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
    if is_dataclass(value):
        return value.__dict__
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value
