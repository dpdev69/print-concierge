import pytest

from print_concierge.public_imports import (
    PublicImportNeedsSlicingError,
    UnsupportedPublicImportError,
    import_public_candidate,
)
from print_concierge.search.base import ModelSearchResult


class FakeImportClient:
    def __init__(self, *, file_hash="sha256:imported-file", file_type="gcode.3mf"):
        self.file_hash = file_hash
        self.file_type = file_type
        self.import_calls = []

    def import_makerworld_model(self, *, model_id, profile_id=None, folder_id=None):
        self.import_calls.append(
            {"model_id": model_id, "profile_id": profile_id, "folder_id": folder_id}
        )
        return {
            "library_file_id": 77,
            "filename": "Headphone Clamp Mount.3mf",
            "folder_id": folder_id,
            "profile_id": profile_id,
            "was_existing": False,
        }

    def get_library_file(self, file_id):
        assert file_id == "77"
        return {
            "id": 77,
            "filename": "Headphone Clamp Mount.3mf",
            "file_hash": self.file_hash,
            "file_type": self.file_type,
            "file_size": 123456,
            "metadata": {
                "source_url": "https://makerworld.com/en/models/1760116#profileId-222",
                "license": "CC-BY",
            },
        }


class FakePublicFileImportClient:
    def __init__(self, *, file_hash="sha256:uploaded-file", file_type="gcode.3mf"):
        self.file_hash = file_hash
        self.file_type = file_type
        self.upload_calls = []

    def upload_library_file(self, *, filename, content, folder_id=None):
        self.upload_calls.append(
            {"filename": filename, "content": content, "folder_id": folder_id}
        )
        return {
            "id": 88,
            "filename": filename,
            "file_type": self.file_type,
            "file_size": len(content),
        }

    def get_library_file(self, file_id):
        assert file_id == "88"
        return {
            "id": 88,
            "filename": "Desk Headphone Holder.gcode.3mf",
            "file_hash": self.file_hash,
            "file_type": self.file_type,
            "file_size": 56789,
            "metadata": {},
        }


class FakeSlicingPublicFileImportClient:
    def __init__(self):
        self.upload_calls = []
        self.slice_calls = []
        self.job_calls = []

    def upload_library_file(self, *, filename, content, folder_id=None):
        self.upload_calls.append(
            {"filename": filename, "content": content, "folder_id": folder_id}
        )
        return {
            "id": 88,
            "filename": filename,
            "file_type": "stl",
            "file_size": len(content),
            "folder_id": folder_id,
        }

    def slice_library_file(self, file_id, slice_options):
        self.slice_calls.append({"file_id": file_id, "slice_options": slice_options})
        return {"job_id": 123, "status": "queued"}

    def get_slice_job(self, job_id):
        self.job_calls.append(job_id)
        return {"id": 123, "status": "completed", "library_file_id": 99}

    def get_library_file(self, file_id):
        if file_id == "88":
            return {
                "id": 88,
                "filename": "headphone-stand.stl",
                "file_hash": "sha256:source-file",
                "file_type": "stl",
                "file_size": 12345,
                "metadata": {},
            }
        assert file_id == "99"
        return {
            "id": 99,
            "filename": "headphone-stand.gcode.3mf",
            "file_hash": "sha256:sliced-file",
            "file_type": "gcode.3mf",
            "file_size": 67890,
            "metadata": {},
        }


def test_import_public_makerworld_candidate_creates_trusted_library_result():
    candidate = ModelSearchResult(
        provider="3dsearch_makerworld",
        result_id="https://3dsearch.net/model/headphone-clamp-mount-for-desk-2-versions-mw1760116",
        title="Headphone Clamp Mount for Desk | 2 Versions",
        source="https://3dsearch.net/model/headphone-clamp-mount-for-desk-2-versions-mw1760116",
        metadata={"origin_site": "MakerWorld"},
    )
    client = FakeImportClient()

    imported = import_public_candidate(
        candidate,
        client=client,
        profile_id=222,
        folder_id=5,
    )

    assert client.import_calls == [{"model_id": 1760116, "profile_id": 222, "folder_id": 5}]
    assert imported.provider == "bambuddy_library"
    assert imported.result_id == "library:77"
    assert imported.title == "Headphone Clamp Mount for Desk | 2 Versions"
    assert imported.file_name == "Headphone Clamp Mount.3mf"
    assert imported.file_hash == "sha256:imported-file"
    assert imported.license == "CC-BY"
    assert imported.metadata["library_file_id"] == "77"
    assert imported.metadata["source_type"] == "makerworld"
    assert imported.metadata["verified"] is True
    assert imported.metadata["public_candidate"]["provider"] == "3dsearch_makerworld"


def test_import_public_printables_direct_queueable_file_uploads_and_verifies():
    candidate = ModelSearchResult(
        provider="3dsearch_printables",
        result_id="https://3dsearch.net/model/headphone-stand-184164",
        title="Desk Headphone Holder",
        source="https://3dsearch.net/model/headphone-stand-184164",
        license="CC-BY",
        metadata={
            "origin_site": "Printables",
            "download_url": "https://media.printables.com/media/prints/184164/files/desk-holder.gcode.3mf",
        },
    )
    client = FakePublicFileImportClient()

    imported = import_public_candidate(
        candidate,
        client=client,
        folder_id=9,
        downloader=lambda url: (b"gcode-3mf-bytes", "Desk Headphone Holder.gcode.3mf"),
    )

    assert client.upload_calls == [
        {
            "filename": "Desk Headphone Holder.gcode.3mf",
            "content": b"gcode-3mf-bytes",
            "folder_id": 9,
        }
    ]
    assert imported.provider == "bambuddy_library"
    assert imported.result_id == "library:88"
    assert imported.file_hash == "sha256:uploaded-file"
    assert imported.license == "CC-BY"
    assert imported.metadata["source_type"] == "printables"
    assert imported.metadata["download_url"] == "https://media.printables.com/media/prints/184164/files/desk-holder.gcode.3mf"
    assert imported.metadata["verified"] is True


def test_import_public_thingiverse_direct_queueable_file_uploads_and_verifies():
    candidate = ModelSearchResult(
        provider="3dsearch_thingiverse",
        result_id="https://3dsearch.net/model/underdesk-headphone-holder-tv4824786",
        title="Underdesk Headphone Holder",
        source="https://3dsearch.net/model/underdesk-headphone-holder-tv4824786",
        metadata={
            "origin_site": "Thingiverse",
            "file": {
                "download_url": "https://cdn.thingiverse.com/assets/ab/underdesk-holder.gcode"
            },
        },
    )
    client = FakePublicFileImportClient(file_type="gcode")

    imported = import_public_candidate(
        candidate,
        client=client,
        downloader=lambda url: (b"; gcode", None),
    )

    assert client.upload_calls[0]["filename"] == "underdesk-holder.gcode"
    assert imported.file_hash == "sha256:uploaded-file"
    assert imported.metadata["source_type"] == "thingiverse"
    assert imported.metadata["file_type"] == "gcode"


def test_import_public_source_geometry_requires_slicing_without_uploading():
    candidate = ModelSearchResult(
        provider="3dsearch_printables",
        result_id="https://3dsearch.net/model/headphone-stand-184164",
        title="Headphone stand",
        source="https://3dsearch.net/model/headphone-stand-184164",
        metadata={
            "origin_site": "Printables",
            "download_url": "https://media.printables.com/media/prints/184164/files/headphone-stand.stl",
        },
    )
    client = FakePublicFileImportClient()

    with pytest.raises(PublicImportNeedsSlicingError, match="sliced"):
        import_public_candidate(
            candidate,
            client=client,
            downloader=lambda url: (b"solid mesh", "headphone-stand.stl"),
        )

    assert client.upload_calls == []


def test_import_public_source_geometry_slices_with_explicit_presets_and_verifies():
    candidate = ModelSearchResult(
        provider="3dsearch_printables",
        result_id="https://3dsearch.net/model/headphone-stand-184164",
        title="Headphone stand",
        source="https://3dsearch.net/model/headphone-stand-184164",
        metadata={
            "origin_site": "Printables",
            "download_url": "https://media.printables.com/media/prints/184164/files/headphone-stand.stl",
        },
    )
    client = FakeSlicingPublicFileImportClient()
    slice_options = {
        "printer_preset": {"source": "standard", "id": "Bambu Lab A1 mini 0.4 nozzle"},
        "process_preset": {"source": "standard", "id": "0.20mm Standard @BBL A1M"},
        "filament_preset": {"source": "standard", "id": "Generic PLA @BBL A1"},
    }

    imported = import_public_candidate(
        candidate,
        client=client,
        folder_id=9,
        downloader=lambda url: (b"solid mesh", "headphone-stand.stl"),
        slice_options=slice_options,
    )

    assert client.upload_calls == [
        {"filename": "headphone-stand.stl", "content": b"solid mesh", "folder_id": 9}
    ]
    assert client.slice_calls == [
        {
            "file_id": "88",
            "slice_options": {**slice_options, "export_3mf": True},
        }
    ]
    assert client.job_calls == ["123"]
    assert imported.provider == "bambuddy_library"
    assert imported.result_id == "library:99"
    assert imported.file_hash == "sha256:sliced-file"
    assert imported.metadata["library_file_id"] == "99"
    assert imported.metadata["source_library_file_id"] == "88"
    assert imported.metadata["slice_job_id"] == "123"
    assert imported.metadata["source_type"] == "printables"
    assert imported.metadata["verified"] is True


def test_import_public_source_geometry_rejects_unknown_slice_option_keys():
    candidate = ModelSearchResult(
        provider="3dsearch_thingiverse",
        result_id="https://3dsearch.net/model/underdesk-headphone-holder-tv4824786",
        title="Underdesk Headphone Holder",
        source="https://3dsearch.net/model/underdesk-headphone-holder-tv4824786",
        metadata={
            "origin_site": "Thingiverse",
            "download_url": "https://cdn.thingiverse.com/assets/ab/holder.stl",
        },
    )

    with pytest.raises(ValueError, match="Unsupported slice option"):
        import_public_candidate(
            candidate,
            client=FakeSlicingPublicFileImportClient(),
            downloader=lambda url: (b"solid mesh", "holder.stl"),
            slice_options={"printer_preset": {"source": "standard", "id": "p"}, "start_now": True},
        )


def test_import_public_rejects_cross_provider_download_url_without_fetching():
    candidate = ModelSearchResult(
        provider="3dsearch_printables",
        result_id="https://3dsearch.net/model/headphone-stand-184164",
        title="Headphone stand",
        source="https://3dsearch.net/model/headphone-stand-184164",
        metadata={
            "origin_site": "Printables",
            "download_url": "https://example.test/headphone-holder.gcode.3mf",
        },
    )
    client = FakePublicFileImportClient()

    with pytest.raises(UnsupportedPublicImportError, match="trusted Printables"):
        import_public_candidate(
            candidate,
            client=client,
            downloader=lambda url: pytest.fail("downloader should not be called"),
        )

    assert client.upload_calls == []


def test_import_public_candidate_rejects_unknown_public_provider_without_calling_client():
    candidate = ModelSearchResult(
        provider="3dsearch_thangs",
        result_id="https://3dsearch.net/model/headphone-stand-th123",
        title="Headphone stand",
        source="https://3dsearch.net/model/headphone-stand-th123",
        metadata={"origin_site": "Thangs"},
    )
    client = FakeImportClient()

    with pytest.raises(UnsupportedPublicImportError, match="MakerWorld, Printables, or Thingiverse"):
        import_public_candidate(candidate, client=client)

    assert client.import_calls == []


def test_import_public_candidate_requires_imported_file_hash():
    candidate = ModelSearchResult(
        provider="3dsearch_makerworld",
        result_id="https://3dsearch.net/model/headphone-clamp-mount-for-desk-2-versions-mw1760116",
        title="Headphone Clamp Mount for Desk | 2 Versions",
        source="https://3dsearch.net/model/headphone-clamp-mount-for-desk-2-versions-mw1760116",
    )

    with pytest.raises(ValueError, match="file hash"):
        import_public_candidate(candidate, client=FakeImportClient(file_hash=None))


def test_import_public_candidate_requires_queueable_sliced_file():
    candidate = ModelSearchResult(
        provider="3dsearch_makerworld",
        result_id="https://3dsearch.net/model/headphone-clamp-mount-for-desk-2-versions-mw1760116",
        title="Headphone Clamp Mount for Desk | 2 Versions",
        source="https://3dsearch.net/model/headphone-clamp-mount-for-desk-2-versions-mw1760116",
    )

    with pytest.raises(ValueError, match="sliced"):
        import_public_candidate(candidate, client=FakeImportClient(file_type="stl"))
