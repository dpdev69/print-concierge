import json

from print_concierge.interfaces.cli import main


class FakeClient:
    def list_printers(self):
        return [{"id": "p1", "name": "A1 mini"}]

    def get_printer_status(self, printer_id):
        return {"id": printer_id, "status": "idle"}

    def list_archives(self):
        return [{"archive_id": "a1", "title": "Cable clip"}]


class FakeArchive:
    def list_archives(self):
        return [{"archive_id": "a1", "title": "Cable clip"}]

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
