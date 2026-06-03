import json

from print_concierge.interfaces.cli import main


class FakeClient:
    def list_printers(self):
        return [{"id": "p1", "name": "A1 mini"}]

    def get_printer_status(self, printer_id):
        return {"id": printer_id, "status": "idle"}

    def list_archives(self):
        return [{"archive_id": "a1", "title": "Cable clip"}]

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


class FakeArchive:
    def list_archives(self):
        return [{"archive_id": "a1", "title": "Cable clip"}]

    def search(self, query, **kwargs):
        from print_concierge.search.base import ModelSearchResult

        return (
            ModelSearchResult(
                provider="local_archive",
                result_id="a1",
                title="Cable clip",
                license="CC0",
                profile="0.20mm",
                source="bambuddy://archives/a1",
                archive_id="a1",
                file_name="clip.3mf",
                file_hash="abc123",
                metadata={"raw": {"access_code": "12345678"}, "score": 0.91},
            ),
        )

    def select(self, archive_id, model_id=None):
        from print_concierge.search.base import ModelSearchResult

        return ModelSearchResult(
            provider="local_archive",
            result_id=f"{archive_id}:{model_id or 'default'}",
            title="Cable clip",
            description="",
            license="CC0",
            profile="0.20mm",
            source="bambuddy://archives/a1",
            archive_id=archive_id,
            model_id=model_id,
            file_name="clip.3mf",
            file_hash="abc123",
        )


def parse(output):
    return json.loads(output.strip())


def test_cli_lists_printers(capsys):
    exit_code = main(["printers"], client=FakeClient(), archive_provider=FakeArchive())

    assert exit_code == 0
    assert parse(capsys.readouterr().out) == [{"id": "p1", "name": "A1 mini"}]


def test_cli_uses_env_configured_bambuddy_client_by_default(monkeypatch, capsys):
    monkeypatch.setattr(
        "print_concierge.interfaces.cli.BambuddyClient", lambda: FakeClient()
    )

    exit_code = main(["archives"])

    assert exit_code == 0
    assert parse(capsys.readouterr().out) == [
        {"archive_id": "a1", "title": "Cable clip"}
    ]


def test_cli_search_returns_normalized_options(capsys):
    exit_code = main(
        ["search", "cable clip", "--limit", "1"],
        archive_provider=FakeArchive(),
    )

    assert exit_code == 0
    output = parse(capsys.readouterr().out)
    assert output == [
        {
            "archive_id": "a1",
            "description": "",
            "file_hash": "abc123",
            "file_name": "clip.3mf",
            "license": "CC0",
            "metadata": {"score": 0.91},
            "model_id": None,
            "profile": "0.20mm",
            "provider": "local_archive",
            "result_id": "a1",
            "source": "bambuddy://archives/a1",
            "title": "Cable clip",
            "warnings": [],
        }
    ]


def test_cli_imports_public_candidate_for_verification(capsys):
    candidate_json = json.dumps(
        {
            "provider": "3dsearch_makerworld",
            "result_id": "https://3dsearch.net/model/headphone-clamp-mount-for-desk-2-versions-mw1760116",
            "title": "Headphone Clamp Mount for Desk | 2 Versions",
            "source": "https://3dsearch.net/model/headphone-clamp-mount-for-desk-2-versions-mw1760116",
        }
    )

    exit_code = main(
        [
            "import-public",
            "--candidate-json",
            candidate_json,
            "--profile-id",
            "222",
            "--folder-id",
            "5",
        ],
        client=FakeClient(),
        archive_provider=FakeArchive(),
    )

    output = parse(capsys.readouterr().out)
    assert exit_code == 0
    assert output["provider"] == "bambuddy_library"
    assert output["metadata"]["library_file_id"] == "77"
    assert output["file_hash"] == "sha256:imported-file"


def test_cli_reports_public_import_status(capsys):
    exit_code = main(["import-status"], client=FakeClient(), archive_provider=FakeArchive())

    output = parse(capsys.readouterr().out)
    assert exit_code == 0
    assert output == {"makerworld": {"can_download": True, "has_cloud_token": True}}


def test_cli_prepares_imported_selected_json_without_queueing(capsys):
    selected_json = json.dumps(
        {
            "provider": "bambuddy_library",
            "result_id": "library:77",
            "title": "Headphone Clamp Mount for Desk | 2 Versions",
            "license": "CC-BY",
            "profile": "222",
            "source": "https://makerworld.com/en/models/1760116",
            "file_name": "Headphone Clamp Mount.3mf",
            "file_hash": "sha256:imported-file",
            "metadata": {"library_file_id": "77", "source_type": "makerworld", "verified": True},
        }
    )

    exit_code = main(
        [
            "prepare-selected",
            "--selected-json",
            selected_json,
            "--printer-id",
            "p1",
            "--material",
            "PLA",
            "--profile",
            "0.20mm",
        ],
        client=FakeClient(),
        archive_provider=FakeArchive(),
    )

    output = parse(capsys.readouterr().out)
    assert exit_code == 0
    assert output["model"]["metadata"]["library_file_id"] == "77"
    assert output["status"] == "confirmation_required"
    assert "confirmation_token" not in output


def test_cli_prepares_plan_without_queueing(capsys):
    exit_code = main(
        [
            "prepare",
            "--archive-id",
            "a1",
            "--printer-id",
            "p1",
            "--material",
            "PLA",
            "--profile",
            "0.20mm",
        ],
        client=FakeClient(),
        archive_provider=FakeArchive(),
    )

    output = parse(capsys.readouterr().out)
    assert exit_code == 0
    assert output["model"]["metadata"]["archive_id"] == "a1"
    assert output["printer"]["printer_id"] == "p1"
    assert output["material_profile"] == "PLA / 0.20mm"
    assert output["status"] == "confirmation_required"
    assert "confirmation_token" not in output
