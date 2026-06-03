import json

import pytest

from print_concierge.models import (
    AuditEvent,
    ConfirmationChallenge,
    ModelSearchResult,
    PolicyConfig,
    PrintPlan,
    PrinterInfo,
    PrinterStateSnapshot,
    RiskFlag,
)


def test_print_plan_requires_core_fields_and_serializes_to_json():
    plan = PrintPlan(
        job_id="job-1",
        user_id="user-1",
        file_hash="sha256:file",
        printer=PrinterInfo(
            printer_id="p1",
            display_name="Bambu Lab A1",
            model="A1",
            serial_number="SN-SECRET",
        ),
        model=ModelSearchResult(
            source="local",
            model_id="benchy",
            title="Benchy",
            file_hash="sha256:file",
        ),
        material_profile="PLA Basic",
        risk_flags=[RiskFlag(label="needs_support", severity="medium", detail="bridges")],
        slicer_settings={"layer_height_mm": 0.2, "supports": False},
        estimated_grams=12.5,
        estimated_minutes=42,
    )

    payload = plan.to_dict()
    assert payload["schema_version"] == 1
    assert payload["printer"]["printer_id"] == "p1"
    assert payload["risk_flags"][0]["label"] == "needs_support"
    json.dumps(payload)

    with pytest.raises(ValueError, match="job_id"):
        PrintPlan(
            job_id="",
            user_id="user-1",
            file_hash="sha256:file",
            printer=plan.printer,
            model=plan.model,
            material_profile="PLA Basic",
        )


def test_plan_hash_is_canonical_and_excludes_volatile_metadata():
    base = PrintPlan(
        job_id="job-1",
        user_id="user-1",
        file_hash="sha256:file",
        printer=PrinterInfo(
            printer_id="p1",
            display_name="A1",
            model="A1",
            current_status="printing",
            cached_thumbnail_url="https://example.test/thumb.png",
        ),
        model=ModelSearchResult(
            source="local",
            model_id="model-1",
            title="Clip",
            file_hash="sha256:file",
            cached_thumbnail_url="https://example.test/model.png",
        ),
        material_profile="PLA Basic",
        slicer_settings={"supports": False, "layer_height_mm": 0.2},
        transient_metadata={"queue_position": 3},
        created_at="2026-06-03T10:00:00Z",
    )
    reordered = PrintPlan(
        job_id="job-1",
        user_id="user-1",
        file_hash="sha256:file",
        printer=PrinterInfo(
            printer_id="p1",
            display_name="A1",
            model="A1",
            current_status="idle",
            cached_thumbnail_url="https://example.test/other.png",
        ),
        model=ModelSearchResult(
            source="local",
            model_id="model-1",
            title="Clip",
            file_hash="sha256:file",
            cached_thumbnail_url="https://example.test/other-model.png",
        ),
        material_profile="PLA Basic",
        slicer_settings={"layer_height_mm": 0.2, "supports": False},
        transient_metadata={"queue_position": 99},
        created_at="2026-06-04T10:00:00Z",
    )
    mutated = PrintPlan(
        job_id="job-1",
        user_id="user-1",
        file_hash="sha256:file",
        printer=base.printer,
        model=base.model,
        material_profile="PETG",
        slicer_settings={"supports": False, "layer_height_mm": 0.2},
    )

    assert base.canonical_json() == reordered.canonical_json()
    assert base.plan_hash == reordered.plan_hash
    assert base.plan_hash != mutated.plan_hash


def test_supporting_models_validate_required_fields_and_have_defaults():
    challenge = ConfirmationChallenge(
        challenge_id="challenge-1",
        user_id="user-1",
        chat_id="chat-1",
        job_id="job-1",
        file_hash="sha256:file",
        printer_id="printer-1",
        material_profile="PLA Basic",
        plan_hash="sha256:plan",
        token_hash="sha256:token",
        expires_at="2026-06-03T10:05:00Z",
    )
    event = AuditEvent(event_type="plan.created")
    policy = PolicyConfig()
    snapshot = PrinterStateSnapshot(printer_id="printer-1", status="idle")

    for item in (challenge, event, policy, snapshot):
        json.dumps(item.to_dict())
        assert item.to_dict()["schema_version"] == 1

    assert policy.require_confirmation is True
    assert "local" in policy.allowed_sources

    with pytest.raises(ValueError, match="event_type"):
        AuditEvent(event_type="")

    with pytest.raises(ValueError, match="printer_id"):
        PrinterStateSnapshot(printer_id="", status="idle")
