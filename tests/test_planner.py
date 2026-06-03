import pytest

from print_concierge.planner import PrintPlan, prepare_print_plan
from print_concierge.models import PrintPlan as CanonicalPrintPlan
from print_concierge.search.base import ModelSearchResult


def selected_result(**overrides):
    data = {
        "provider": "local_archive",
        "result_id": "archive-1:model-1",
        "title": "Cable clip",
        "description": "Tidy cable clip",
        "license": "CC0",
        "profile": "0.20mm",
        "source": "bambuddy://archives/archive-1/models/model-1",
        "archive_id": "archive-1",
        "model_id": "model-1",
        "file_name": "clip.3mf",
        "file_hash": "sourcehash",
        "warnings": (),
    }
    data.update(overrides)
    return ModelSearchResult(**data)


def test_prepare_print_plan_uses_source_hash_and_does_not_generate_confirmation():
    plan = prepare_print_plan(
        selected=selected_result(),
        printer={"id": "p1", "name": "A1 mini", "model": "A1", "status": "idle", "fresh": True, "provenance": "bambuddy"},
        material={"type": "PLA", "color": "black", "fresh": True, "provenance": "bambuddy"},
        profile={"name": "0.20mm", "nozzle": "0.4", "fresh": True, "provenance": "bambuddy"},
        user_id="user-1",
        session_id="session-1",
    )

    assert isinstance(plan, PrintPlan)
    assert isinstance(plan, CanonicalPrintPlan)
    assert plan.file_hash == "sourcehash"
    assert plan.status.value == "confirmation_required"
    assert plan.plan_hash.startswith("sha256:")
    assert "confirmation_token" not in plan.to_dict()


def test_prepare_print_plan_preserves_imported_library_file_identity():
    plan = prepare_print_plan(
        selected=ModelSearchResult(
            provider="bambuddy_library",
            result_id="library:77",
            title="Headphone Clamp Mount for Desk | 2 Versions",
            license="CC-BY",
            profile="0.2mm",
            source="https://makerworld.com/en/models/1760116",
            file_name="Headphone Clamp Mount.3mf",
            file_hash="sha256:imported-file",
            metadata={"library_file_id": "77", "source_type": "makerworld", "verified": True},
        ),
        printer={"id": "p1", "name": "A1 mini", "model": "A1", "fresh": True, "provenance": "bambuddy"},
        material={"type": "PLA", "fresh": True, "provenance": "bambuddy"},
        profile={"name": "0.2mm", "fresh": True, "provenance": "bambuddy"},
        user_id="u1",
        session_id="s1",
    )

    assert plan.model.metadata["library_file_id"] == "77"
    assert plan.model.metadata["source_type"] == "makerworld"
    assert plan.model.metadata["verified"] is True


def test_prepare_print_plan_hashes_file_bytes_when_provided():
    plan = prepare_print_plan(
        selected=selected_result(file_hash="sourcehash"),
        printer={"id": "p1", "name": "A1 mini", "model": "A1", "status": "idle", "fresh": True, "provenance": "bambuddy"},
        material={"type": "PLA", "color": "green", "fresh": True, "provenance": "bambuddy"},
        profile={"name": "0.20mm", "nozzle": "0.4", "fresh": True, "provenance": "bambuddy"},
        user_id="user-1",
        session_id="session-1",
        file_bytes=b"print data",
    )

    assert plan.file_hash == "0362ce4ea18320589bd7b179391ccfb7edabab78b6e46bdcdd55e52a460414da"


def test_prepare_print_plan_rejects_missing_required_printer_material_profile_data():
    with pytest.raises(ValueError, match="printer.id"):
        prepare_print_plan(
            selected=selected_result(),
            printer={"name": "A1 mini"},
            material={"type": "PLA", "fresh": True, "provenance": "bambuddy"},
            profile={"name": "0.20mm", "fresh": True, "provenance": "bambuddy"},
            user_id="user-1",
            session_id="session-1",
        )


def test_prepare_print_plan_rejects_missing_freshness_and_provenance():
    with pytest.raises(ValueError, match="printer.fresh"):
        prepare_print_plan(
            selected=selected_result(),
            printer={"id": "p1", "name": "A1 mini", "model": "A1", "provenance": "bambuddy"},
            material={"type": "PLA", "fresh": True, "provenance": "bambuddy"},
            profile={"name": "0.20mm", "fresh": True, "provenance": "bambuddy"},
            user_id="user-1",
            session_id="session-1",
        )

    with pytest.raises(ValueError, match="material.provenance"):
        prepare_print_plan(
            selected=selected_result(),
            printer={"id": "p1", "name": "A1 mini", "model": "A1", "fresh": True, "provenance": "bambuddy"},
            material={"type": "PLA", "fresh": True},
            profile={"name": "0.20mm", "fresh": True, "provenance": "bambuddy"},
            user_id="user-1",
            session_id="session-1",
        )


def test_prepare_print_plan_deep_freezes_payloads():
    plan = prepare_print_plan(
        selected=selected_result(),
        printer={
            "id": "p1",
            "name": "A1 mini",
            "model": "A1",
            "fresh": True,
            "provenance": "bambuddy",
            "capabilities": {"ams": True},
        },
        material={"type": "PLA", "fresh": True, "provenance": "bambuddy"},
        profile={"name": "0.20mm", "fresh": True, "provenance": "bambuddy", "settings": {"layer_height": 0.2}},
        user_id="user-1",
        session_id="session-1",
    )

    with pytest.raises(TypeError):
        plan.printer.capabilities["ams"] = False
    with pytest.raises(TypeError):
        plan.slicer_settings["profile"]["settings"]["layer_height"] = 0.28


def test_prepare_print_plan_rejects_missing_file_identity():
    with pytest.raises(ValueError, match="file hash"):
        prepare_print_plan(
            selected=selected_result(file_hash=None),
            printer={"id": "p1", "name": "A1 mini", "model": "A1", "fresh": True, "provenance": "bambuddy"},
            material={"type": "PLA", "fresh": True, "provenance": "bambuddy"},
            profile={"name": "0.20mm", "fresh": True, "provenance": "bambuddy"},
            user_id="user-1",
            session_id="session-1",
        )
