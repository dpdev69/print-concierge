from __future__ import annotations

import hashlib
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Tuple

from print_concierge.models import (
    ModelSearchResult as CanonicalModelSearchResult,
    PrintPlan,
    PrinterInfo,
    PrintPlanStatus,
    RiskFlag,
)
from print_concierge.search.base import ModelSearchResult


def prepare_print_plan(
    *,
    selected: ModelSearchResult | Mapping[str, Any],
    printer: Mapping[str, Any],
    material: Mapping[str, Any],
    profile: Mapping[str, Any],
    user_id: str,
    session_id: str,
    file_bytes: bytes | None = None,
    file_path: str | Path | None = None,
    confirmation_service: Any = None,
    print_client: Any = None,
) -> PrintPlan:
    result = _coerce_result(selected)
    _validate_required("printer", printer, ("id", "name", "model"))
    _validate_required("material", material, ("type",))
    _validate_required("profile", profile, ("name",))
    _validate_fresh("printer", printer)
    _validate_fresh("material", material)
    _validate_fresh("profile", profile)

    file_hash = _resolve_file_hash(result, file_bytes=file_bytes, file_path=file_path)
    job_id = _stable_job_id(
        selected=result,
        printer=printer,
        material=material,
        profile=profile,
        user_id=user_id,
        session_id=session_id,
        file_hash=file_hash,
    )

    canonical_model = CanonicalModelSearchResult(
        source=result.provider,
        model_id=result.model_id or result.result_id,
        title=result.title,
        file_hash=file_hash,
        url=result.source,
        license=result.license,
        metadata=_freeze(
            {
                "archive_id": result.archive_id,
                "description": result.description,
                "file_name": result.file_name,
                "profile": result.profile,
                "provider_result_id": result.result_id,
                "source": result.source,
                "warnings": result.warnings,
                **_trusted_model_metadata(result.metadata),
            }
        ),
    )
    printer_info = PrinterInfo(
        printer_id=str(printer["id"]),
        display_name=str(printer["name"]),
        model=str(printer["model"]),
        current_status=str(printer["status"]) if printer.get("status") else None,
        capabilities=_freeze(dict(printer.get("capabilities") or {})),
    )

    return PrintPlan(
        job_id=job_id,
        user_id=str(user_id),
        file_hash=file_hash,
        printer=printer_info,
        model=canonical_model,
        material_profile=f"{material['type']} / {profile['name']}",
        risk_flags=_risk_flags(result),
        slicer_settings=_freeze(
            {
                "material": dict(material),
                "profile": dict(profile),
                "session_id": str(session_id),
            }
        ),
        transient_metadata=_freeze(
            {
                "queues_disabled": True,
                "confirmation_generated": False,
            }
        ),
        status=PrintPlanStatus.CONFIRMATION_REQUIRED,
    )


def _coerce_result(selected: ModelSearchResult | Mapping[str, Any]) -> ModelSearchResult:
    if isinstance(selected, ModelSearchResult):
        return selected
    return ModelSearchResult(**dict(selected))


def _validate_required(name: str, data: Mapping[str, Any], keys: tuple[str, ...]) -> None:
    for key in keys:
        if not data.get(key):
            raise ValueError(f"{name}.{key} is required")


def _validate_fresh(name: str, data: Mapping[str, Any]) -> None:
    if data.get("stale") is True:
        raise ValueError(f"{name} data is stale")
    if data.get("fresh") is not True:
        raise ValueError(f"{name}.fresh must be true for preparation")
    if not data.get("provenance"):
        raise ValueError(f"{name}.provenance is required")


def _trusted_model_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "file_size",
        "file_type",
        "folder_id",
        "library_file_id",
        "makerworld_model_id",
        "makerworld_profile_id",
        "source_type",
        "verified",
        "was_existing",
    }
    return {key: metadata[key] for key in allowed_keys if key in metadata}


def _resolve_file_hash(
    selected: ModelSearchResult,
    *,
    file_bytes: bytes | None,
    file_path: str | Path | None,
) -> str:
    if file_bytes is not None:
        return hashlib.sha256(file_bytes).hexdigest()
    if file_path is not None:
        return hashlib.sha256(Path(file_path).read_bytes()).hexdigest()
    if selected.file_hash:
        return str(selected.file_hash)
    raise ValueError("file hash is required from file bytes, file path, source, or archive data")


def _risk_flags(selected: ModelSearchResult) -> Tuple[RiskFlag, ...]:
    labels = list(selected.warnings)
    if selected.provider == "local_archive" and not selected.model_id:
        labels.append("manual_archive_selection")
    if not selected.license:
        labels.append("license_unverified")
    return tuple(
        RiskFlag(label=label, severity="warning", detail="Generated during print plan preparation.")
        for label in dict.fromkeys(labels)
    )


def _stable_job_id(
    *,
    selected: ModelSearchResult,
    printer: Mapping[str, Any],
    material: Mapping[str, Any],
    profile: Mapping[str, Any],
    user_id: str,
    session_id: str,
    file_hash: str,
) -> str:
    digest = hashlib.sha256(
        "|".join(
            [
                selected.provider,
                selected.result_id,
                str(printer["id"]),
                str(material["type"]),
                str(profile["name"]),
                file_hash,
                str(user_id),
                str(session_id),
            ]
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"plan-{digest}"


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value
