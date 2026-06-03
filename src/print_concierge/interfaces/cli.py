from __future__ import annotations

import argparse
import json
import sys
from dataclasses import is_dataclass
from typing import Any, Sequence

from print_concierge.bambuddy import BambuddyClient, BambuddyError
from print_concierge.planner import PrintPlan, prepare_print_plan
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
    confirmation_service: Any = None,
    output: Any = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    out = output or sys.stdout
    client = client if client is not None else _default_client()
    archive_provider = archive_provider or _default_archive_provider(client)
    search_provider = search_provider or _default_search_provider(archive_provider)

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
    elif args.command == "confirm":
        if confirmation_service is None:
            raise SystemExit("confirm requires an injected confirmation service in this build")
        if hasattr(confirmation_service, "request_confirmation"):
            _emit(out, confirmation_service.request_confirmation(args.plan_id))
        else:
            raise SystemExit("confirm requires plan-bound confirmation details")
    elif args.command == "queue":
        if client is None:
            raise SystemExit("queue requires an injected Bambuddy client in this build")
        if hasattr(client, "queue_confirmed_print"):
            _emit(out, client.queue_confirmed_print(args.confirmation_token))
        else:
            raise SystemExit("queue requires a confirmation-aware queue gateway")
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
    subparsers.add_parser("archives")
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--archive-id", required=True)
    prepare.add_argument("--model-id")
    prepare.add_argument("--printer-id", required=True)
    prepare.add_argument("--material", required=True)
    prepare.add_argument("--profile", required=True)
    prepare.add_argument("--user-id", default="cli-user")
    prepare.add_argument("--session-id", default="cli-session")
    confirm = subparsers.add_parser("confirm")
    confirm.add_argument("plan_id")
    queue = subparsers.add_parser("queue")
    queue.add_argument("confirmation_token")
    return parser


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
        return value.to_dict()
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
