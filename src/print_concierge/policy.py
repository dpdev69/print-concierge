from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
