from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ModelSearchResult:
    provider: str
    result_id: str
    title: str
    description: str = ""
    license: Optional[str] = None
    profile: Optional[str] = None
    source: Optional[str] = None
    archive_id: Optional[str] = None
    model_id: Optional[str] = None
    file_name: Optional[str] = None
    file_hash: Optional[str] = None
    warnings: Tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "result_id": self.result_id,
            "title": self.title,
            "description": self.description,
            "license": self.license,
            "profile": self.profile,
            "source": self.source,
            "archive_id": self.archive_id,
            "model_id": self.model_id,
            "file_name": self.file_name,
            "file_hash": self.file_hash,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


class SearchProvider(ABC):
    provider_name: str

    @abstractmethod
    def search(self, query: str, **kwargs: Any) -> Sequence[ModelSearchResult]:
        raise NotImplementedError


def normalize_result(provider: str, raw: Mapping[str, Any]) -> ModelSearchResult:
    """Normalize provider data while keeping provider text as inert strings."""

    result_id = _first_text(raw, "result_id", "id", "model_id", "archive_id") or "unknown"
    title = _first_text(raw, "title", "name", "file_name") or "Untitled model"
    description = _first_text(raw, "description", "summary", "notes") or ""
    license_name = _first_text(raw, "license", "license_name")
    profile = _profile_text(raw)
    source = _first_text(raw, "source", "source_url", "url", "origin")
    archive_id = _first_text(raw, "archive_id", "archiveId")
    model_id = _first_text(raw, "model_id", "modelId")
    file_name = _file_text(raw, "name") or _first_text(raw, "file_name", "filename")
    file_hash = _file_text(raw, "sha256") or _file_text(raw, "hash") or _first_text(raw, "file_hash", "sha256", "hash")

    warnings = []
    if not license_name:
        warnings.append("missing_license")
    if not profile:
        warnings.append("missing_profile")
    if not source:
        warnings.append("missing_source")

    return ModelSearchResult(
        provider=str(provider),
        result_id=str(result_id),
        title=str(title),
        description=str(description),
        license=license_name,
        profile=profile,
        source=source,
        archive_id=archive_id,
        model_id=model_id,
        file_name=file_name,
        file_hash=file_hash,
        warnings=tuple(warnings),
        metadata={"raw": dict(raw)},
    )


def _first_text(raw: Mapping[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = raw.get(key)
        if value is not None and value != "":
            return str(value)
    return None


def _profile_text(raw: Mapping[str, Any]) -> Optional[str]:
    value = raw.get("profile") or raw.get("print_profile") or raw.get("profile_name")
    if isinstance(value, Mapping):
        nested = value.get("name") or value.get("id")
        return str(nested) if nested else None
    if value:
        return str(value)
    return None


def _file_text(raw: Mapping[str, Any], key: str) -> Optional[str]:
    value = raw.get("file")
    if isinstance(value, Mapping):
        nested = value.get(key)
        if nested:
            return str(nested)
    return None
