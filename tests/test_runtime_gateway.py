import sqlite3
import stat

import pytest

from print_concierge.interfaces import mcp_server
from print_concierge.runtime import RuntimeApprovalService, RuntimeQueueGateway, RuntimeState
from print_concierge.search.base import ModelSearchResult


class QueueClient:
    def __init__(self):
        self.payloads = []

    def queue_print(self, payload):
        self.payloads.append(payload)
        return {"job_id": "42", "status": "pending", "queue_item": {"id": 42}}


class FailingQueueClient:
    def queue_print(self, payload):
        raise RuntimeError("network down")


def _plan():
    return mcp_server.prepare_print_plan(
        selected=ModelSearchResult(
            provider="local_archive",
            result_id="8",
            title="Cable holder",
            license="CC0",
            profile="0.2mm",
            source="https://makerworld.com/en/models/1282635",
            archive_id="8",
            file_name="holder.3mf",
            file_hash="abc123",
        ),
        printer={
            "id": "1",
            "name": "A1 Mini",
            "model": "A1 Mini",
            "fresh": True,
            "provenance": "bambuddy",
        },
        material={"type": "PLA", "fresh": True, "provenance": "bambuddy"},
        profile={"name": "0.2mm", "fresh": True, "provenance": "bambuddy"},
        user_id="user-1",
        session_id="chat-1",
    )


def test_runtime_print_request_persists_plan_and_never_returns_authorizing_token(tmp_path):
    state = RuntimeState(tmp_path / "state.sqlite3")
    service = RuntimeApprovalService(state)

    request = service.create_print_request(_plan())

    assert request["request_id"].startswith("req_")
    assert request["status"] == "pending_user_approval"
    assert request["job_id"].startswith("plan-")
    assert "token" not in request
    assert "confirmation_token" not in request
    database_text = (tmp_path / "state.sqlite3").read_bytes()
    assert b"pc_" not in database_text
    assert state.get_plan(request["plan_hash"])["job_id"] == request["job_id"]


def test_runtime_print_request_rejects_forged_plan_hash(tmp_path):
    state = RuntimeState(tmp_path / "state.sqlite3")
    service = RuntimeApprovalService(state)
    plan = _plan()
    forged = {**plan, "plan_hash": "sha256:not-the-plan"}

    with pytest.raises(ValueError, match="plan_hash"):
        service.create_print_request(forged)


def test_runtime_queue_gateway_queues_pending_request_once(tmp_path):
    state = RuntimeState(tmp_path / "state.sqlite3")
    service = RuntimeApprovalService(state)
    queue_client = QueueClient()
    gateway = RuntimeQueueGateway(state, queue_client)
    request = service.create_print_request(_plan())

    queued = gateway.queue_print_request(request["request_id"])

    assert queued["job_id"] == "42"
    assert queue_client.payloads[0]["_print_concierge_confirmed"] is True
    assert queue_client.payloads[0]["approval"]["request_id"] == request["request_id"]
    assert queue_client.payloads[0]["plan_hash"] == request["plan_hash"]
    status = service.get_print_request_status(request["request_id"])
    assert status["status"] == "queued"
    assert status["queue_job_id"] == "42"
    with pytest.raises(ValueError, match="already used"):
        gateway.queue_print_request(request["request_id"])


def test_runtime_queue_gateway_rejects_duplicate_queue_claim(tmp_path):
    state = RuntimeState(tmp_path / "state.sqlite3")
    service = RuntimeApprovalService(state)
    request = service.create_print_request(_plan())

    claimed, _ = state.claim_request_for_queue(request["request_id"])

    assert claimed["status"] == "queueing"
    with pytest.raises(ValueError, match="already queueing"):
        RuntimeQueueGateway(state, QueueClient()).queue_print_request(request["request_id"])


def test_runtime_queue_gateway_marks_failed_request_without_retrying(tmp_path):
    state = RuntimeState(tmp_path / "state.sqlite3")
    service = RuntimeApprovalService(state)
    gateway = RuntimeQueueGateway(state, FailingQueueClient())
    request = service.create_print_request(_plan())

    with pytest.raises(RuntimeError, match="network down"):
        gateway.queue_print_request(request["request_id"])

    status = service.get_print_request_status(request["request_id"])
    assert status["status"] == "failed"
    assert "network down" in status["queue_error"]
    with pytest.raises(ValueError, match="failed"):
        gateway.queue_print_request(request["request_id"])


def test_mcp_default_print_request_uses_runtime_state(monkeypatch, tmp_path):
    state_path = tmp_path / "state.sqlite3"
    monkeypatch.setenv("PRINT_CONCIERGE_STATE_DB", str(state_path))

    request = mcp_server.create_print_request(_plan())
    status = mcp_server.get_print_request_status(request["request_id"])

    assert request["status"] == "pending_user_approval"
    assert "token" not in request
    assert status["request_id"] == request["request_id"]
    assert status["status"] == "pending_user_approval"


def test_runtime_state_initializes_required_tables(tmp_path):
    RuntimeState(tmp_path / "state.sqlite3").initialize()

    with sqlite3.connect(tmp_path / "state.sqlite3") as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    assert {"print_plans", "print_requests", "queue_results"} <= tables


def test_runtime_state_uses_private_filesystem_permissions(tmp_path):
    state_path = tmp_path / "private" / "state.sqlite3"

    RuntimeState(state_path).initialize()

    assert stat.S_IMODE(state_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
