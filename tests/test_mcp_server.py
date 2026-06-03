import inspect
import sys
import types

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
                metadata={"raw": {"serial_number": "ABC123"}, "score": 0.9},
            ),
        )


class FakeArchiveClient:
    def list_archives(self):
        return [
            {
                "archive_id": "runtime-a1",
                "model_id": "runtime-m1",
                "title": "Runtime cable clip",
                "license": "CC0",
                "profile": "0.20mm",
                "source": "bambuddy://archives/runtime-a1",
            }
        ]


class FakeExternalProvider:
    def search(self, query, **kwargs):
        return (
            ModelSearchResult(
                provider="external",
                result_id=f"ext:{query}",
                title=f"External {query}",
                description="",
                license="CC0",
                profile="0.20mm",
                source="https://example.test/model",
            ),
        )


class FakeImportClient:
    def get_makerworld_status(self):
        return {"has_cloud_token": True, "can_download": True}

    def import_makerworld_model(self, *, model_id, profile_id=None, folder_id=None):
        return {
            "library_file_id": 77,
            "filename": "Headphone Clamp Mount.3mf",
            "folder_id": folder_id,
            "profile_id": profile_id,
            "was_existing": False,
        }

    def get_library_file(self, file_id):
        return {
            "id": 77,
            "filename": "Headphone Clamp Mount.3mf",
            "file_hash": "sha256:imported-file",
            "file_type": "gcode.3mf",
            "file_size": 123456,
            "metadata": {"source_url": "https://makerworld.com/en/models/1760116"},
        }


class FakeLimitedProvider:
    def __init__(self):
        self.kwargs = None

    def search(self, query, **kwargs):
        self.kwargs = kwargs
        return (
            ModelSearchResult(
                provider="external",
                result_id="ext-1",
                title="First",
                license="CC0",
                profile="0.20mm",
                source="https://example.test/1",
            ),
            ModelSearchResult(
                provider="external",
                result_id="ext-2",
                title="Second",
                license="CC0",
                profile="0.20mm",
                source="https://example.test/2",
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
    assert mcp_server.search_archive_or_models("clip", archive_provider=FakeArchive())[0]["metadata"] == {"score": 0.9}


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


def test_mcp_registered_tool_wrappers_hide_injected_runtime_objects(monkeypatch):
    captured = []

    class FakeFastMCP:
        def __init__(self, name):
            self.name = name

        def tool(self):
            def register(func):
                captured.append(func)
                return func

            return register

        def run(self):
            return None

    monkeypatch.setitem(sys.modules, "mcp", types.ModuleType("mcp"))
    monkeypatch.setitem(sys.modules, "mcp.server", types.ModuleType("mcp.server"))
    fake_fastmcp = types.ModuleType("mcp.server.fastmcp")
    fake_fastmcp.FastMCP = FakeFastMCP
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", fake_fastmcp)

    mcp_server.main()

    registered = {func.__name__: inspect.signature(func) for func in captured}
    assert "search_archive_or_models" in registered
    forbidden = {
        "archive_provider",
        "client",
        "confirmation_service",
        "print_client",
        "search_provider",
    }
    for signature in registered.values():
        assert forbidden.isdisjoint(signature.parameters)


def test_default_search_uses_runtime_archive_and_external_providers(monkeypatch):
    monkeypatch.setattr(mcp_server, "_default_bambuddy_client", lambda: FakeArchiveClient())
    monkeypatch.setattr(mcp_server, "_configured_external_search_providers", lambda: [FakeExternalProvider()])
    monkeypatch.setattr(mcp_server, "_default_public_search_provider", lambda: None)

    results = mcp_server.search_archive_or_models("clip")

    assert [result["title"] for result in results] == ["Runtime cable clip", "External clip"]


def test_mcp_search_accepts_limit_for_public_tool_shape():
    provider = FakeLimitedProvider()

    results = mcp_server.search_archive_or_models("clip", limit=1, search_provider=provider)

    assert provider.kwargs == {"limit": 1}
    assert [result["title"] for result in results] == ["First"]


def test_mcp_import_public_candidate_returns_trusted_library_result():
    result = mcp_server.import_public_candidate(
        {
            "provider": "3dsearch_makerworld",
            "result_id": "https://3dsearch.net/model/headphone-clamp-mount-for-desk-2-versions-mw1760116",
            "title": "Headphone Clamp Mount for Desk | 2 Versions",
            "source": "https://3dsearch.net/model/headphone-clamp-mount-for-desk-2-versions-mw1760116",
        },
        client=FakeImportClient(),
        profile_id=222,
        folder_id=5,
    )

    assert result["provider"] == "bambuddy_library"
    assert result["metadata"]["library_file_id"] == "77"
    assert result["file_hash"] == "sha256:imported-file"


def test_mcp_public_import_status_reports_makerworld_download_readiness():
    assert mcp_server.get_public_import_status(client=FakeImportClient()) == {
        "makerworld": {"has_cloud_token": True, "can_download": True}
    }


def test_mcp_job_status_degrades_when_client_has_no_job_status_method():
    assert mcp_server.get_job_status("job-1", client=FakeArchiveClient()) == {
        "job_id": "job-1",
        "status": "unknown",
    }
