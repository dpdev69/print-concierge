import json

import httpx
import pytest

from print_concierge.bambuddy.client import (
    BambuddyAmbiguousActionError,
    BambuddyClient,
    BambuddyError,
    BambuddyNotFoundError,
)


TEST_API_KEY = "fake-unit-test-key"


def _client(handler, monkeypatch):
    monkeypatch.setenv("BAMBUDDY_BASE_URL", "https://printer.local")
    monkeypatch.setenv("BAMBUDDY_API_KEY", TEST_API_KEY)
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    return BambuddyClient(http_client=http_client)


def test_env_config_headers_and_list_printers_path(monkeypatch):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["api_key"] = request.headers.get("X-API-Key")
        return httpx.Response(200, json=[{"id": "p1"}])

    client = _client(handler, monkeypatch)

    assert client.list_printers() == [{"id": "p1"}]
    assert seen == {
        "url": "https://printer.local/api/v1/printers/",
        "api_key": TEST_API_KEY,
    }
    assert TEST_API_KEY not in repr(client)


def test_known_read_methods_use_expected_paths(monkeypatch):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={"ok": True})

    client = _client(handler, monkeypatch)

    client.get_printer("p1")
    client.get_printer_status("p1")
    client.list_archives()
    client.get_archive("a1")
    client.get_snapshot("p1")

    assert paths == [
        "/api/v1/printers/p1",
        "/api/v1/printers/p1/status",
        "/api/v1/archives/",
        "/api/v1/archives/a1",
        "/api/v1/printers/p1/camera/snapshot",
    ]


def test_queue_print_posts_plan_and_returns_job_id(monkeypatch):
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["json"] = request.read()
        return httpx.Response(202, json={"job_id": "job-1"})

    client = _client(handler, monkeypatch)

    assert client.queue_print(
        {
            "archive_id": "1",
            "printer_id": "2",
            "_print_concierge_confirmed": True,
        }
    ) == {"job_id": "job-1", "queue_item": {"job_id": "job-1"}, "status": "queued"}
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/v1/queue/"
    assert json.loads(seen["json"])["archive_id"] == 1
    assert json.loads(seen["json"])["printer_id"] == 2


def test_queue_print_maps_confirmed_archive_plan_to_bambuddy_queue_payload(monkeypatch):
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["payload"] = json.loads(request.read())
        return httpx.Response(
            200,
            json={
                "id": 42,
                "status": "pending",
                "archive_id": 8,
                "printer_id": 1,
                "manual_start": True,
            },
        )

    client = _client(handler, monkeypatch)

    result = client.queue_print(
        {
            "_print_concierge_confirmed": True,
            "job_id": "plan-1",
            "plan_hash": "sha256:plan",
            "material_profile": "PLA / 0.2mm",
            "printer": {"printer_id": "1"},
            "model": {"metadata": {"archive_id": "8"}},
        }
    )

    assert result == {
        "job_id": "42",
        "status": "pending",
        "queue_item": {
            "id": 42,
            "status": "pending",
            "archive_id": 8,
            "printer_id": 1,
            "manual_start": True,
        },
    }
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/v1/queue/"
    assert seen["payload"] == {
        "archive_id": 8,
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
    }


def test_get_job_status_reads_queue_item(monkeypatch):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={"id": 42, "status": "printing"})

    client = _client(handler, monkeypatch)

    assert client.get_job_status("42") == {
        "job_id": "42",
        "status": "printing",
        "queue_item": {"id": 42, "status": "printing"},
    }
    assert paths == ["/api/v1/queue/42"]


def test_queue_print_requires_internal_confirmation_marker(monkeypatch):
    client = _client(lambda request: httpx.Response(202, json={"job_id": "job-1"}), monkeypatch)

    with pytest.raises(BambuddyError, match="confirmed"):
        client.queue_print({"archive_id": "a1"})


def test_ambiguous_queue_response_fails_without_assuming_success(monkeypatch):
    def handler(request):
        return httpx.Response(202, json={"status": "queued"})

    client = _client(handler, monkeypatch)

    with pytest.raises(BambuddyAmbiguousActionError):
        client.queue_print(
            {
                "archive_id": "1",
                "printer_id": "2",
                "_print_concierge_confirmed": True,
            }
        )


def test_errors_do_not_expose_api_key(monkeypatch):
    def handler(request):
        return httpx.Response(500, json={"error": "boom"})

    client = _client(handler, monkeypatch)

    with pytest.raises(BambuddyError) as exc:
        client.list_printers()

    assert TEST_API_KEY not in str(exc.value)


def test_responses_redact_sensitive_printer_fields(monkeypatch):
    def handler(request):
        return httpx.Response(
            200,
            json=[
                {
                    "id": "p1",
                    "access_code": "12345678",
                    "serial_number": "ABC123",
                    "nested": {"token": "should-not-leak", "name": "kept"},
                }
            ],
        )

    client = _client(handler, monkeypatch)

    assert client.list_printers() == [
        {
            "id": "p1",
            "access_code": "<redacted>",
            "serial_number": "<redacted>",
            "nested": {"token": "<redacted>", "name": "kept"},
        }
    ]


def test_not_found_raises_specific_error(monkeypatch):
    def handler(request):
        return httpx.Response(404, json={"error": "missing"})

    client = _client(handler, monkeypatch)

    with pytest.raises(BambuddyNotFoundError):
        client.get_printer("missing")


def test_endpoint_allowlist_blocks_unknown_paths(monkeypatch):
    client = _client(lambda request: httpx.Response(200, json={}), monkeypatch)

    with pytest.raises(BambuddyError):
        client._request("GET", "/api/v1/direct-start")


def test_endpoint_allowlist_blocks_unknown_printer_subpaths(monkeypatch):
    client = _client(lambda request: httpx.Response(200, json={}), monkeypatch)

    with pytest.raises(BambuddyError):
        client._request("GET", "/api/v1/printers/p1/direct-start")
