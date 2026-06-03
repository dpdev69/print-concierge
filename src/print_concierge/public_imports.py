from __future__ import annotations

import re
from typing import Any, Mapping

from print_concierge.search.base import ModelSearchResult


class UnsupportedPublicImportError(ValueError):
    pass


def import_public_candidate(
    selected: ModelSearchResult | Mapping[str, Any],
    *,
    client: Any,
    profile_id: int | str | None = None,
    folder_id: int | str | None = None,
) -> ModelSearchResult:
    result = _coerce_result(selected)
    makerworld_id = _makerworld_model_id(result)
    if makerworld_id is None:
        raise UnsupportedPublicImportError(
            "V1.1 automatic import currently supports MakerWorld candidates only."
        )
    if client is None or not hasattr(client, "import_makerworld_model"):
        raise TypeError("import_public_candidate requires a Bambuddy import client")

    resolved_profile_id = _int_or_none(profile_id) or _makerworld_profile_id(result)
    resolved_folder_id = _int_or_none(folder_id)
    import_result = dict(
        client.import_makerworld_model(
            model_id=makerworld_id,
            profile_id=resolved_profile_id,
            folder_id=resolved_folder_id,
        )
    )
    library_file_id = import_result.get("library_file_id") or import_result.get("id")
    if library_file_id is None:
        raise ValueError("MakerWorld import response did not include library_file_id")
    if not hasattr(client, "get_library_file"):
        raise TypeError("import_public_candidate requires get_library_file verification")

    file_info = dict(client.get_library_file(str(library_file_id)))
    file_hash = file_info.get("file_hash") or file_info.get("hash")
    if not file_hash:
        raise ValueError("imported public candidate is missing a file hash")
    file_type = str(file_info.get("file_type") or "").casefold()
    if file_type and file_type not in {"gcode", "gcode.3mf"}:
        raise ValueError("imported public candidate must be a sliced gcode/gcode.3mf file")

    metadata = file_info.get("metadata") if isinstance(file_info.get("metadata"), Mapping) else {}
    source_url = (
        metadata.get("source_url")
        or metadata.get("makerworld_url")
        or result.source
        or f"https://makerworld.com/en/models/{makerworld_id}"
    )
    imported_profile = import_result.get("profile_id") or resolved_profile_id
    license_name = metadata.get("license") or result.license

    return ModelSearchResult(
        provider="bambuddy_library",
        result_id=f"library:{library_file_id}",
        title=result.title,
        description=result.description,
        license=str(license_name) if license_name else None,
        profile=str(imported_profile) if imported_profile is not None else result.profile,
        source=str(source_url) if source_url else None,
        model_id=str(makerworld_id),
        file_name=str(file_info.get("filename") or import_result.get("filename") or result.file_name),
        file_hash=str(file_hash),
        warnings=(),
        metadata={
            "library_file_id": str(library_file_id),
            "folder_id": str(import_result["folder_id"])
            if import_result.get("folder_id") is not None
            else None,
            "source_type": "makerworld",
            "makerworld_model_id": str(makerworld_id),
            "makerworld_profile_id": str(imported_profile)
            if imported_profile is not None
            else None,
            "file_type": file_info.get("file_type"),
            "file_size": file_info.get("file_size"),
            "was_existing": bool(import_result.get("was_existing", False)),
            "verified": True,
            "public_candidate": result.to_public_dict(),
        },
    )


def _coerce_result(selected: ModelSearchResult | Mapping[str, Any]) -> ModelSearchResult:
    if isinstance(selected, ModelSearchResult):
        return selected
    return ModelSearchResult(**dict(selected))


def _makerworld_model_id(result: ModelSearchResult) -> int | None:
    if not _looks_like_makerworld(result):
        return None
    values = (
        result.model_id,
        result.result_id,
        result.source,
        result.metadata.get("source_url"),
        result.metadata.get("makerworld_url"),
        result.metadata.get("model_id"),
    )
    for value in values:
        text = str(value or "")
        direct = _int_or_none(text)
        if direct is not None:
            return direct
        for pattern in (r"/models/(\d+)", r"\bmw(\d+)\b", r"profileId-\d+.*?(\d+)"):
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return int(match.group(1))
    return None


def _makerworld_profile_id(result: ModelSearchResult) -> int | None:
    values = (
        result.metadata.get("profile_id"),
        result.metadata.get("makerworld_profile_id"),
        result.result_id,
        result.source,
    )
    for value in values:
        text = str(value or "")
        direct = _int_or_none(text)
        if direct is not None and value in values[:2]:
            return direct
        match = re.search(r"profileId-(\d+)", text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _looks_like_makerworld(result: ModelSearchResult) -> bool:
    haystack = " ".join(
        str(value or "")
        for value in (
            result.provider,
            result.source,
            result.result_id,
            result.metadata.get("origin_site"),
            result.metadata.get("source_type"),
            result.metadata.get("source_url"),
        )
    ).casefold()
    return "makerworld" in haystack or re.search(r"\bmw\d+\b", haystack) is not None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
