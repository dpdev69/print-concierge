import pytest

from print_concierge.bambuddy.client import BambuddyClient, BambuddyError
from print_concierge.bambuddy.sandbox import SandboxBambuddyClient


def _confirmed_archive_plan():
    return {
        "_print_concierge_confirmed": True,
        "job_id": "plan-headphone-cable-holder",
        "plan_hash": "sha256:demo-headphone-cable-holder",
        "material_profile": "PLA / 0.20mm",
        "printer": {"printer_id": "1"},
        "model": {
            "title": "Headphone and cable holder",
            "metadata": {"archive_id": "101"},
        },
    }


def test_sandbox_exposes_clear_demo_fixture_data():
    client = SandboxBambuddyClient()

    assert client.list_printers() == [
        {
            "id": "1",
            "printer_id": "1",
            "name": "Sandbox A1 Mini",
            "model": "Bambu Lab A1 mini",
            "status": "idle",
            "sandbox": True,
        }
    ]
    assert client.get_printer_status("1") == {
        "id": "1",
        "printer_id": "1",
        "status": "idle",
        "current_task": None,
        "sandbox": True,
    }
    assert client.list_archives() == [
        {
            "archive_id": "101",
            "model_id": "demo-headphone-cable-holder",
            "title": "Headphone and Cable Holder",
            "description": "Demo clamp for holding headphones and routing a charging cable.",
            "license": "CC0-1.0",
            "profile": "0.20mm Standard",
            "source": "bambuddy://sandbox/archives/101",
            "file_name": "headphone-cable-holder-demo.3mf",
            "file_hash": "sha256:sandbox-headphone-cable-holder",
        }
    ]
    assert client.list_slicer_presets() == {
        "printers": [{"id": "a1-mini-0.4", "name": "Bambu Lab A1 mini 0.4 nozzle"}],
        "processes": [{"id": "0.20mm-standard", "name": "0.20mm Standard"}],
        "filaments": [{"id": "generic-pla", "name": "Generic PLA"}],
    }
    assert client.get_makerworld_status() == {
        "status": "sandbox",
        "can_download": True,
        "has_cloud_token": False,
        "network": False,
    }


def test_sandbox_queue_print_requires_internal_confirmation_marker():
    client = SandboxBambuddyClient()

    with pytest.raises(BambuddyError, match="approved"):
        client.queue_print({"archive_id": "101", "printer_id": "1"})


def test_sandbox_queue_print_mimics_real_queue_contract_without_network(monkeypatch):
    def fail_request(*args, **kwargs):
        raise AssertionError("sandbox client must not call the network request path")

    monkeypatch.setattr(BambuddyClient, "_request", fail_request)
    client = SandboxBambuddyClient()

    first = client.queue_print(_confirmed_archive_plan())
    second = SandboxBambuddyClient().queue_print(_confirmed_archive_plan())

    assert first["job_id"] == second["job_id"]
    assert first == {
        "job_id": first["job_id"],
        "status": "pending_manual_start",
        "queue_item": {
            "id": first["job_id"],
            "job_id": first["job_id"],
            "status": "pending_manual_start",
            "archive_id": 101,
            "bed_levelling": True,
            "flow_cali": False,
            "gcode_injection": False,
            "layer_inspect": False,
            "manual_start": True,
            "printer_id": 1,
            "quantity": 1,
            "required_filament_types": ["PLA"],
            "timelapse": False,
            "use_ams": True,
            "vibration_cali": True,
            "sandbox": True,
            "hardware_touched": False,
            "network_calls": 0,
            "source_plan_job_id": "plan-headphone-cable-holder",
            "source_plan_hash": "sha256:demo-headphone-cable-holder",
        },
    }
    assert first["job_id"].startswith("sandbox-queue-")
    assert client.get_job_status(first["job_id"]) == first


def test_sandbox_queue_print_preserves_manual_start_env_override(monkeypatch):
    monkeypatch.setenv("PRINT_CONCIERGE_BAMBUDDY_MANUAL_START", "false")

    queued = SandboxBambuddyClient().queue_print(_confirmed_archive_plan())

    assert queued["status"] == "queued"
    assert queued["queue_item"]["manual_start"] is False


def test_sandbox_queue_print_supports_library_file_plans():
    plan = _confirmed_archive_plan()
    plan["model"]["metadata"] = {"library_file_id": "202"}

    queued = SandboxBambuddyClient().queue_print(plan)

    assert queued["queue_item"]["library_file_id"] == 202
    assert "archive_id" not in queued["queue_item"]


def test_sandbox_queue_print_reuses_real_payload_validation():
    plan = _confirmed_archive_plan()
    plan["model"]["metadata"] = {}

    with pytest.raises(BambuddyError, match="archive_id or library_file_id"):
        SandboxBambuddyClient().queue_print(plan)
