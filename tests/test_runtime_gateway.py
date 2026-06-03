import sqlite3
import stat

import pytest

from print_concierge.interfaces import mcp_server
from print_concierge.runtime import RuntimeConfirmationService, RuntimeQueueGateway, RuntimeState
from print_concierge.search.base import ModelSearchResult


class QueueClient:
    def __init__(self):
        self.payloads = []

    def queue_print(self, payload):
        self.payloads.append(payload)
        return {"job_id": "42", "status": "pending", "queue_item": {"id": 42}}


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


def test_runtime_confirmation_persists_plan_and_never_stores_plaintext_token(tmp_path):
    state = RuntimeState(tmp_path / "state.sqlite3")
    service = RuntimeConfirmationService(state)

    challenge = service.request_confirmation(_plan())

    assert challenge["token"].startswith("pc_")
    assert challenge["job_id"].startswith("plan-")
    database_text = (tmp_path / "state.sqlite3").read_bytes()
    assert challenge["token"].encode() not in database_text
    assert state.get_plan(challenge["plan_hash"])["job_id"] == challenge["job_id"]


def test_runtime_queue_gateway_consumes_token_once_and_queues_confirmed_plan(tmp_path):
    state = RuntimeState(tmp_path / "state.sqlite3")
    service = RuntimeConfirmationService(state)
    queue_client = QueueClient()
    gateway = RuntimeQueueGateway(state, queue_client)
    challenge = service.request_confirmation(_plan())

    queued = gateway.queue_confirmed_print(challenge["token"])

    assert queued["job_id"] == "42"
    assert queue_client.payloads[0]["_print_concierge_confirmed"] is True
    assert queue_client.payloads[0]["confirmation"]["challenge_id"] == challenge["challenge_id"]
    assert queue_client.payloads[0]["plan_hash"] == challenge["plan_hash"]
    with pytest.raises(ValueError, match="already used"):
        gateway.queue_confirmed_print(challenge["token"])


def test_mcp_default_confirmation_and_queue_gateway_use_runtime_state(monkeypatch, tmp_path):
    state_path = tmp_path / "state.sqlite3"
    queue_client = QueueClient()
    monkeypatch.setenv("PRINT_CONCIERGE_STATE_DB", str(state_path))
    monkeypatch.setattr(mcp_server, "_default_bambuddy_client", lambda: queue_client)

    challenge = mcp_server.request_confirmation(_plan())
    queued = mcp_server.queue_confirmed_print(challenge["token"])

    assert queued["job_id"] == "42"
    assert queue_client.payloads[0]["_print_concierge_confirmed"] is True


def test_runtime_state_initializes_required_tables(tmp_path):
    RuntimeState(tmp_path / "state.sqlite3").initialize()

    with sqlite3.connect(tmp_path / "state.sqlite3") as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    assert {"print_plans", "confirmation_challenges", "queue_results"} <= tables


def test_runtime_state_uses_private_filesystem_permissions(tmp_path):
    state_path = tmp_path / "private" / "state.sqlite3"

    RuntimeState(state_path).initialize()

    assert stat.S_IMODE(state_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
