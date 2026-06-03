from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional


SCHEMA_VERSION = 1
VOLATILE_FIELDS = {
    "cached_thumbnail_url",
    "created_at",
    "current_status",
    "last_seen_at",
    "status",
    "timestamps",
    "transient_metadata",
    "updated_at",
}


class PrintPlanStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMATION_REQUIRED = "confirmation_required"
    CONFIRMED = "confirmed"
    QUEUED = "queued"


class ConfirmationChallengeStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    EXPIRED = "expired"
    CANCELED = "canceled"


def _require_non_empty(value: Optional[str], name: str) -> None:
    if value is None or not str(value).strip():
        raise ValueError(f"{name} is required")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize(value: Any, *, exclude_volatile: bool = False) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _normalize(value.to_dict(), exclude_volatile=exclude_volatile)
    if isinstance(value, Mapping):
        result: Dict[str, Any] = {}
        for key, item in value.items():
            key_text = unicodedata.normalize("NFC", str(key))
            if exclude_volatile and key_text in VOLATILE_FIELDS:
                continue
            result[key_text] = _normalize(item, exclude_volatile=exclude_volatile)
        return {key: result[key] for key in sorted(result)}
    if isinstance(value, (list, tuple)):
        return [_normalize(item, exclude_volatile=exclude_volatile) for item in value]
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    return value


class SerializableDataclass:
    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        for item in fields(self):
            value = getattr(self, item.name)
            if value is None:
                continue
            payload[item.name] = _normalize(value)
        return payload


@dataclass(frozen=True)
class ModelSearchResult(SerializableDataclass):
    source: str
    model_id: str
    title: str
    file_hash: str
    url: Optional[str] = None
    author: Optional[str] = None
    license: Optional[str] = None
    cached_thumbnail_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("source", "model_id", "title", "file_hash"):
            _require_non_empty(getattr(self, name), name)


@dataclass(frozen=True)
class PrinterInfo(SerializableDataclass):
    printer_id: str
    display_name: str
    model: str
    serial_number: Optional[str] = None
    firmware_version: Optional[str] = None
    capabilities: Dict[str, Any] = field(default_factory=dict)
    current_status: Optional[str] = None
    cached_thumbnail_url: Optional[str] = None
    camera_url: Optional[str] = None

    def __post_init__(self) -> None:
        for name in ("printer_id", "display_name", "model"):
            _require_non_empty(getattr(self, name), name)


@dataclass(frozen=True)
class RiskFlag(SerializableDataclass):
    label: str
    severity: str
    detail: str = ""

    def __post_init__(self) -> None:
        for name in ("label", "severity"):
            _require_non_empty(getattr(self, name), name)


@dataclass(frozen=True)
class PrintPlan(SerializableDataclass):
    job_id: str
    user_id: str
    file_hash: str
    printer: PrinterInfo
    model: ModelSearchResult
    material_profile: str
    schema_version: int = SCHEMA_VERSION
    risk_flags: List[RiskFlag] = field(default_factory=list)
    slicer_settings: Dict[str, Any] = field(default_factory=dict)
    estimated_grams: Optional[float] = None
    estimated_minutes: Optional[int] = None
    created_at: str = field(default_factory=_utc_now_iso)
    transient_metadata: Dict[str, Any] = field(default_factory=dict)
    status: PrintPlanStatus = PrintPlanStatus.DRAFT

    def __post_init__(self) -> None:
        for name in ("job_id", "user_id", "file_hash", "material_profile"):
            _require_non_empty(getattr(self, name), name)
        if not isinstance(self.printer, PrinterInfo):
            raise ValueError("printer must be PrinterInfo")
        if not isinstance(self.model, ModelSearchResult):
            raise ValueError("model must be ModelSearchResult")

    def canonical_payload(self) -> Dict[str, Any]:
        return _normalize(self.to_dict(), exclude_volatile=True)

    def canonical_json(self) -> str:
        return json.dumps(
            self.canonical_payload(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @property
    def plan_hash(self) -> str:
        digest = hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
        return f"sha256:{digest}"


@dataclass(frozen=True)
class ConfirmationChallenge(SerializableDataclass):
    challenge_id: str
    user_id: str
    chat_id: str
    job_id: str
    file_hash: str
    printer_id: str
    material_profile: str
    plan_hash: str
    token_hash: str
    expires_at: str
    schema_version: int = SCHEMA_VERSION
    status: ConfirmationChallengeStatus = ConfirmationChallengeStatus.PENDING
    created_at: str = field(default_factory=_utc_now_iso)

    def __post_init__(self) -> None:
        for name in (
            "challenge_id",
            "user_id",
            "chat_id",
            "job_id",
            "file_hash",
            "printer_id",
            "material_profile",
            "plan_hash",
            "token_hash",
            "expires_at",
        ):
            _require_non_empty(getattr(self, name), name)


@dataclass(frozen=True)
class AuditEvent(SerializableDataclass):
    event_type: str
    actor_id: Optional[str] = None
    job_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION
    created_at: str = field(default_factory=_utc_now_iso)

    def __post_init__(self) -> None:
        _require_non_empty(self.event_type, "event_type")


@dataclass(frozen=True)
class PolicyConfig(SerializableDataclass):
    require_confirmation: bool = True
    token_ttl_seconds: int = 300
    allowed_sources: List[str] = field(default_factory=lambda: ["local", "archive"])
    max_estimated_minutes_without_warning: int = 480
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class PrinterStateSnapshot(SerializableDataclass):
    printer_id: str
    status: str
    captured_at: str = field(default_factory=_utc_now_iso)
    material_loaded: Optional[str] = None
    bed_temperature_c: Optional[float] = None
    nozzle_temperature_c: Optional[float] = None
    queue_depth: Optional[int] = None
    details: Dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(self.printer_id, "printer_id")
        _require_non_empty(self.status, "status")
