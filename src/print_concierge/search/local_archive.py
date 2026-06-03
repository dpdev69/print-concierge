from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from print_concierge.search.base import ModelSearchResult, SearchProvider, normalize_result


class LocalArchiveSearchProvider(SearchProvider):
    provider_name = "local_archive"

    def __init__(self, archives: Iterable[Mapping[str, Any]] | None = None):
        self._archives = tuple(archives or ())

    def list_archives(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._archives]

    def search(self, query: str, **kwargs: Any) -> Sequence[ModelSearchResult]:
        needle = query.casefold()
        results = []
        for item in self._archives:
            haystack = " ".join(
                str(item.get(key, ""))
                for key in (
                    "title",
                    "print_name",
                    "name",
                    "filename",
                    "file_name",
                    "description",
                    "archive_id",
                    "archiveId",
                    "id",
                    "model_id",
                    "modelId",
                )
            ).casefold()
            if not needle or needle in haystack:
                results.append(_normalize_archive_item(item))
        return tuple(results)

    def select(self, archive_id: str, model_id: str | None = None) -> ModelSearchResult:
        for item in self._archives:
            if str(_archive_id(item)) != str(archive_id):
                continue
            if model_id is not None and str(_model_id(item)) != str(model_id):
                continue
            return _normalize_archive_item(item)
        raise LookupError("archive/model selection was not found")


def _normalize_archive_item(item: Mapping[str, Any]) -> ModelSearchResult:
    archive_id = _archive_id(item)
    model_id = _model_id(item)
    raw = dict(item)
    raw.setdefault("archive_id", archive_id)
    if model_id is not None:
        raw.setdefault("model_id", model_id)
    if archive_id and model_id:
        raw.setdefault("result_id", f"{archive_id}:{model_id}")
    elif archive_id:
        raw.setdefault("result_id", str(archive_id))
    source_keys = ("source", "source_url", "url", "origin", "makerworld_url", "external_url")
    if archive_id and not any(raw.get(key) for key in source_keys):
        raw["source"] = f"bambuddy://archives/{archive_id}"
    return normalize_result(LocalArchiveSearchProvider.provider_name, raw)


def _archive_id(item: Mapping[str, Any]) -> Any:
    return item.get("archive_id") or item.get("archiveId") or item.get("id")


def _model_id(item: Mapping[str, Any]) -> Any:
    return item.get("model_id") or item.get("modelId")
