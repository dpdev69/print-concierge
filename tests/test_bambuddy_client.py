import httpx
import pytest

from print_concierge.bambuddy.client import (
    BambuddyAmbiguousActionError,
    BambuddyClient,
    BambuddyError,
    BambuddyNotFoundError,
)


def _client(handler, monkeypatch):
    monkeypatch.setenv("BAMBUDDY_BASE_URL", "https://printer.local")
    monkeypatch.setenv("BAMBUDDY_API_KEY", "super-secret-key")
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
        "api_key": "super-secret-key",
    }
    assert "super-secret-key" not in repr(client)


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

    assert client.queue_print({"archive_id": "a1", "_print_concierge_confirmed": True}) == {"job_id": "job-1"}
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/v1/queue/"
    assert b"a1" in seen["json"]


def test_queue_print_requires_internal_confirmation_marker(monkeypatch):
    client = _client(lambda request: httpx.Response(202, json={"job_id": "job-1"}), monkeypatch)

    with pytest.raises(BambuddyError, match="confirmed"):
        client.queue_print({"archive_id": "a1"})


def test_ambiguous_queue_response_fails_without_assuming_success(monkeypatch):
    def handler(request):
        return httpx.Response(202, json={"status": "queued"})

    client = _client(handler, monkeypatch)

    with pytest.raises(BambuddyAmbiguousActionError):
        client.queue_print({"archive_id": "a1", "_print_concierge_confirmed": True})


def test_errors_do_not_expose_api_key(monkeypatch):
    def handler(request):
        return httpx.Response(500, json={"error": "boom"})

    client = _client(handler, monkeypatch)

    with pytest.raises(BambuddyError) as exc:
        client.list_printers()

    assert "super-secret-key" not in str(exc.value)


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
