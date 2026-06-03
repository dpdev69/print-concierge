from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


CAPABILITY_MODES = frozenset({"search_only", "prepare_only", "queue_enabled", "admin"})


@dataclass(frozen=True)
class PolicyConfig:
    confirmation_required_actions: frozenset[str] = frozenset(
        {"queue_print", "start_print"}
    )
    allow_raw_gcode: bool = False
    high_temp_materials: frozenset[str] = frozenset(
        {"ABS", "ASA", "NYLON", "PC", "POLYCARBONATE"}
    )
    max_duration_minutes: int | None = 8 * 60
    deny_long_duration_jobs: bool = False
    allowed_users: frozenset[str] | set[str] | None = None
    allowed_chats: frozenset[str] | set[str] | None = None
    allowed_printers: frozenset[str] | set[str] | None = None
    require_snapshot_for_remote: bool = False
    capability_mode: str = "queue_enabled"

    def __post_init__(self) -> None:
        if self.capability_mode not in CAPABILITY_MODES:
            raise ValueError(
                "capability_mode must be one of: "
                + ", ".join(sorted(CAPABILITY_MODES))
            )

    @classmethod
    def from_env(cls) -> "PolicyConfig":
        return cls(
            capability_mode=os.environ.get(
                "PRINT_CONCIERGE_CAPABILITY_MODE", "queue_enabled"
            ).strip()
            or "queue_enabled",
            allowed_users=_csv_env("PRINT_CONCIERGE_ALLOWED_USERS"),
            allowed_chats=_csv_env("PRINT_CONCIERGE_ALLOWED_CHATS"),
            allowed_printers=_csv_env("PRINT_CONCIERGE_ALLOWED_PRINTERS"),
            deny_long_duration_jobs=_bool_env(
                "PRINT_CONCIERGE_DENY_LONG_DURATION_JOBS", default=False
            ),
            allow_raw_gcode=_bool_env("PRINT_CONCIERGE_ALLOW_RAW_GCODE", default=False),
            require_snapshot_for_remote=_bool_env(
                "PRINT_CONCIERGE_REQUIRE_SNAPSHOT_FOR_REMOTE", default=False
            ),
            max_duration_minutes=_int_env(
                "PRINT_CONCIERGE_MAX_DURATION_MINUTES", default=8 * 60
            ),
        )


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)


class PolicyEngine:
    def __init__(self, config: PolicyConfig | None = None) -> None:
        self.config = config or PolicyConfig()

    def evaluate(
        self,
        *,
        action: str,
        plan: dict[str, Any] | None = None,
        user_id: str | None = None,
        chat_id: str | None = None,
        printer_id: str | None = None,
        confirmation_id: str | None = None,
        remote: bool = False,
        snapshot_id: str | None = None,
        client_text: str | None = None,
    ) -> PolicyDecision:
        del client_text
        plan = plan or {}
        reasons: list[str] = []
        risk_flags: list[str] = []

        self._check_allowlist(
            "user", user_id, self.config.allowed_users, reasons, risk_flags
        )
        self._check_allowlist(
            "chat", chat_id, self.config.allowed_chats, reasons, risk_flags
        )
        self._check_allowlist(
            "printer", printer_id, self.config.allowed_printers, reasons, risk_flags
        )

        if (
            action in {"queue_print", "start_print"}
            and self.config.capability_mode in {"search_only", "prepare_only"}
        ):
            reasons.append(
                f"Capability mode {self.config.capability_mode!r} disables queueing."
            )
            risk_flags.append("queue_disabled_by_capability_mode")

        if action in self.config.confirmation_required_actions and not confirmation_id:
            reasons.append(f"Action {action!r} requires explicit confirmation.")
            risk_flags.append("missing_confirmation")

        if not self.config.allow_raw_gcode and self._contains_raw_gcode(plan):
            reasons.append("Raw G-code is blocked by default.")
            risk_flags.append("raw_gcode")

        material = self._material_name(plan)
        if material in self.config.high_temp_materials:
            reasons.append(f"Material {material} requires high-temperature handling.")
            risk_flags.append("high_temp_material")

        estimated_minutes = self._duration_minutes(plan)
        max_minutes = self.config.max_duration_minutes
        if (
            estimated_minutes is not None
            and max_minutes is not None
            and estimated_minutes > max_minutes
        ):
            reasons.append(
                f"Estimated duration {estimated_minutes:g} minutes exceeds "
                f"configured limit of {max_minutes:g} minutes."
            )
            risk_flags.append("long_duration")

        if remote and self.config.require_snapshot_for_remote and not snapshot_id:
            reasons.append("Remote print requires a recent printer snapshot.")
            risk_flags.append("snapshot_required")

        denying_flags = {
            "missing_confirmation",
            "raw_gcode",
            "user_not_allowed",
            "chat_not_allowed",
            "printer_not_allowed",
            "queue_disabled_by_capability_mode",
            "snapshot_required",
        }
        if self.config.deny_long_duration_jobs:
            denying_flags.add("long_duration")

        allowed = not any(flag in denying_flags for flag in risk_flags)
        return PolicyDecision(allowed=allowed, reasons=reasons, risk_flags=risk_flags)

    @staticmethod
    def _check_allowlist(
        label: str,
        value: str | None,
        allowed_values: frozenset[str] | set[str] | None,
        reasons: list[str],
        risk_flags: list[str],
    ) -> None:
        if allowed_values is None:
            return
        if value not in allowed_values:
            reasons.append(f"{label.title()} is not allowed by policy.")
            risk_flags.append(f"{label}_not_allowed")

    @staticmethod
    def _contains_raw_gcode(plan: dict[str, Any]) -> bool:
        if plan.get("raw_gcode"):
            return True
        if plan.get("gcode"):
            return True
        source_type = str(plan.get("source_type", "")).lower()
        return source_type in {"gcode", "raw_gcode"}

    @staticmethod
    def _material_name(plan: dict[str, Any]) -> str:
        slicer_settings = plan.get("slicer_settings")
        if isinstance(slicer_settings, dict):
            material = slicer_settings.get("material")
            if isinstance(material, dict):
                value = material.get("type") or material.get("name")
                if value:
                    return str(value).upper()
        material_profile = plan.get("material_profile")
        if material_profile:
            return str(material_profile).split("/", 1)[0].strip().upper()
        return str(plan.get("material", "")).upper()

    @staticmethod
    def _duration_minutes(plan: dict[str, Any]) -> float | None:
        value = plan.get("estimated_minutes", plan.get("duration_minutes"))
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


def _csv_env(name: str) -> frozenset[str] | None:
    value = os.environ.get(name)
    if value is None:
        return None
    items = frozenset(item.strip() for item in value.split(",") if item.strip())
    return items or None


def _bool_env(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, *, default: int | None) -> int | None:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    if value.strip().lower() in {"none", "off", "false"}:
        return None
    return int(value)
