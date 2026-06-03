import pytest

from print_concierge.public_imports import UnsupportedPublicImportError, import_public_candidate
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


def test_import_public_candidate_rejects_unsupported_public_provider_without_calling_client():
    candidate = ModelSearchResult(
        provider="3dsearch_printables",
        result_id="https://3dsearch.net/model/headphone-stand-184164",
        title="Headphone stand",
        source="https://3dsearch.net/model/headphone-stand-184164",
        metadata={"origin_site": "Printables"},
    )
    client = FakeImportClient()

    with pytest.raises(UnsupportedPublicImportError, match="MakerWorld"):
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
