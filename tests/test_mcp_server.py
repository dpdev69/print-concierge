import pytest

from print_concierge.interfaces import mcp_server
from print_concierge.search.base import ModelSearchResult


class FakeClient:
    def list_printers(self):
        return [{"id": "p1", "name": "A1 mini"}]

    def get_printer_status(self, printer_id):
        return {"id": printer_id, "status": "idle"}

    def queue_confirmed_print(self, confirmation_token):
        return {"job_id": "job-1", "token": confirmation_token}

    def queue_print(self, payload):
        raise AssertionError("raw queue_print must not be called with only a token")

    def get_job_status(self, job_id):
        return {"job_id": job_id, "status": "queued"}


class FakeArchive:
    def search(self, query):
        return (
            ModelSearchResult(
                provider="local_archive",
                result_id="a1:m1",
                title="Cable clip",
                description="",
                license="CC0",
                profile="0.20mm",
                source="bambuddy://archives/a1",
                archive_id="a1",
                model_id="m1",
                file_name="clip.3mf",
                file_hash="abc123",
            ),
        )


class FakeConfirmation:
    def __init__(self):
        self.last_payload = None

    def request_confirmation(self, plan):
        self.last_payload = plan
        return {"token": "confirm-1", "job_id": plan["job_id"]}


def test_mcp_tool_functions_are_callable_without_mcp_sdk():
    assert mcp_server.list_printers(client=FakeClient()) == [{"id": "p1", "name": "A1 mini"}]
    assert mcp_server.get_printer_status("p1", client=FakeClient())["status"] == "idle"
    assert mcp_server.search_archive_or_models("clip", archive_provider=FakeArchive())[0]["title"] == "Cable clip"


def test_mcp_confirmation_and_queue_are_separate_steps():
    selected = FakeArchive().search("clip")[0]
    plan = mcp_server.prepare_print_plan(
        selected=selected,
        printer={"id": "p1", "name": "A1 mini", "model": "A1", "fresh": True, "provenance": "bambuddy"},
        material={"type": "PLA", "fresh": True, "provenance": "bambuddy"},
        profile={"name": "0.20mm", "fresh": True, "provenance": "bambuddy"},
        user_id="u1",
        session_id="s1",
    )

    confirmation = mcp_server.request_confirmation(plan, confirmation_service=FakeConfirmation())
    queued = mcp_server.queue_confirmed_print("confirm-1", client=FakeClient())

    assert "confirmation_token" not in plan
    assert confirmation["token"] == "confirm-1"
    assert confirmation["job_id"] == plan["job_id"]
    assert queued["job_id"] == "job-1"


def test_mcp_queue_refuses_raw_bambuddy_client_token_only_bypass():
    class RawClient:
        def queue_print(self, payload):
            raise AssertionError("queue_print bypass should not be reached")

    with pytest.raises(TypeError, match="queue gateway"):
        mcp_server.queue_confirmed_print("confirm-1", client=RawClient())


def test_mcp_queue_rejects_ambiguous_gateway_response():
    class AmbiguousGateway:
        def queue_confirmed_print(self, confirmation_token):
            return {"status": "queued"}

    with pytest.raises(ValueError, match="job_id"):
        mcp_server.queue_confirmed_print("confirm-1", client=AmbiguousGateway())


def test_mcp_request_confirmation_uses_plan_hash_and_session_binding():
    selected = FakeArchive().search("clip")[0]
    plan = mcp_server.prepare_print_plan(
        selected=selected,
        printer={"id": "p1", "name": "A1 mini", "model": "A1", "fresh": True, "provenance": "bambuddy"},
        material={"type": "PLA", "fresh": True, "provenance": "bambuddy"},
        profile={"name": "0.20mm", "fresh": True, "provenance": "bambuddy"},
        user_id="u1",
        session_id="mcp-session-7",
    )
    confirmation = FakeConfirmation()

    payload = mcp_server.request_confirmation(plan, confirmation_service=confirmation)

    assert payload["token"] == "confirm-1"
    assert confirmation.last_payload["plan_hash"].startswith("sha256:")
    assert confirmation.last_payload["session_id"] == "mcp-session-7"


def test_mcp_request_confirmation_rejects_dict_without_plan_hash_or_session():
    with pytest.raises(ValueError, match="plan_hash"):
        mcp_server.request_confirmation(
            {
                "job_id": "job-1",
                "user_id": "u1",
                "file_hash": "sha256:file",
                "printer": {"printer_id": "p1"},
                "material_profile": "PLA / 0.20mm",
            },
            confirmation_service=FakeConfirmation(),
        )
