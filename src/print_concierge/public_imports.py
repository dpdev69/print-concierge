from __future__ import annotations

import os
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping
from urllib.parse import unquote, urljoin, urlsplit

import httpx

from print_concierge.search.base import ModelSearchResult


class UnsupportedPublicImportError(ValueError):
    pass


class PublicImportNeedsSlicingError(ValueError):
    pass


@dataclass(frozen=True)
class DownloadedPublicFile:
    content: bytes
    filename: str | None = None


Downloader = Callable[[str], DownloadedPublicFile | tuple[bytes, str | None] | bytes]

_QUEUEABLE_FILE_TYPES = {"gcode", "gcode.3mf"}
_QUEUEABLE_FILENAME_SUFFIXES = (".gcode", ".gcode.3mf")
_SOURCE_FILE_TYPES = {"3mf", "stl", "step", "stp", "obj", "amf"}
_SOURCE_FILENAME_SUFFIXES = (".stl", ".step", ".stp", ".obj", ".amf")
_ALLOWED_SLICE_OPTION_KEYS = {
    "printer_preset_id",
    "process_preset_id",
    "filament_preset_id",
    "printer_preset",
    "process_preset",
    "filament_preset",
    "filament_presets",
    "bundle",
    "plate",
    "export_3mf",
    "bed_type",
}
_DIRECT_URL_KEYS = {
    "download_url",
    "downloadurl",
    "direct_download_url",
    "directdownloadurl",
    "file_url",
    "fileurl",
    "source_file_url",
    "sourcefileurl",
    "source_download_url",
    "sourcedownloadurl",
}
_FILENAME_KEYS = {"filename", "file_name", "name"}
_PROVIDER_LABELS = {
    "makerworld": "MakerWorld",
    "printables": "Printables",
    "thingiverse": "Thingiverse",
}
_TRUSTED_DOWNLOAD_DOMAINS = {
    "printables": ("printables.com",),
    "thingiverse": ("thingiverse.com",),
}


def import_public_candidate(
    selected: ModelSearchResult | Mapping[str, Any],
    *,
    client: Any,
    profile_id: int | str | None = None,
    folder_id: int | str | None = None,
    downloader: Downloader | None = None,
    slice_options: Mapping[str, Any] | None = None,
    slice_wait_seconds: float | None = None,
) -> ModelSearchResult:
    result = _coerce_result(selected)
    provider = _public_import_provider(result)
    if provider == "makerworld":
        return _import_makerworld_candidate(
            result,
            client=client,
            profile_id=profile_id,
            folder_id=folder_id,
        )
    if provider in {"printables", "thingiverse"}:
        return _import_trusted_file_candidate(
            result,
            provider=provider,
            client=client,
            folder_id=folder_id,
            downloader=downloader,
            slice_options=slice_options,
            slice_wait_seconds=slice_wait_seconds,
        )
    raise UnsupportedPublicImportError(
        "Automatic public import currently supports MakerWorld, Printables, or "
        "Thingiverse candidates only."
    )


def _import_makerworld_candidate(
    result: ModelSearchResult,
    *,
    client: Any,
    profile_id: int | str | None,
    folder_id: int | str | None,
) -> ModelSearchResult:
    makerworld_id = _makerworld_model_id(result)
    if makerworld_id is None:
        raise UnsupportedPublicImportError(
            "MakerWorld import requires a MakerWorld model id."
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


def _import_trusted_file_candidate(
    result: ModelSearchResult,
    *,
    provider: str,
    client: Any,
    folder_id: int | str | None,
    downloader: Downloader | None,
    slice_options: Mapping[str, Any] | None,
    slice_wait_seconds: float | None,
) -> ModelSearchResult:
    if client is None or not hasattr(client, "upload_library_file"):
        raise TypeError("import_public_candidate requires a Bambuddy upload client")
    if not hasattr(client, "get_library_file"):
        raise TypeError("import_public_candidate requires get_library_file verification")

    download_url = _trusted_download_url(result, provider)
    filename_hint = _trusted_download_filename(download_url) or _metadata_filename(result)
    normalized_slice_options = _normalize_slice_options(slice_options)
    if filename_hint and _is_source_filename(filename_hint) and not normalized_slice_options:
        raise PublicImportNeedsSlicingError(
            f"{_PROVIDER_LABELS[provider]} source geometry must be sliced before it "
            "can be queued as a print."
        )

    downloaded = _coerce_downloaded(
        (downloader or (lambda url: _download_public_file(url, provider=provider)))(
            download_url
        )
    )
    filename = _safe_filename(downloaded.filename or filename_hint)
    if _is_source_filename(filename) and not normalized_slice_options:
        raise PublicImportNeedsSlicingError(
            f"{_PROVIDER_LABELS[provider]} source geometry must be sliced before it "
            "can be queued as a print."
        )
    if not downloaded.content:
        raise ValueError("downloaded public candidate is empty")

    upload_result = dict(
        client.upload_library_file(
            filename=filename,
            content=downloaded.content,
            folder_id=_int_or_none(folder_id),
        )
    )
    library_file_id = upload_result.get("id") or upload_result.get("library_file_id")
    if library_file_id is None:
        raise ValueError("public file upload response did not include a library file id")

    file_info = dict(client.get_library_file(str(library_file_id)))
    if _is_queueable_file_info(file_info):
        return _trusted_library_result(
            result,
            import_result=upload_result,
            file_info=file_info,
            library_file_id=library_file_id,
            source_type=provider,
            source_url=result.source,
            download_url=download_url,
        )
    if not normalized_slice_options:
        file_type = str(file_info.get("file_type") or "").casefold()
        if file_type in _SOURCE_FILE_TYPES or _is_source_filename(filename):
            raise PublicImportNeedsSlicingError(
                "imported public candidate must be sliced before it can be queued."
            )
        return _trusted_library_result(
            result,
            import_result=upload_result,
            file_info=file_info,
            library_file_id=library_file_id,
            source_type=provider,
            source_url=result.source,
            download_url=download_url,
        )
    sliced_file_id, slice_job_id = _slice_uploaded_public_file(
        client,
        source_library_file_id=str(library_file_id),
        slice_options=normalized_slice_options,
        wait_seconds=slice_wait_seconds,
    )
    sliced_file_info = dict(client.get_library_file(str(sliced_file_id)))
    return _trusted_library_result(
        result,
        import_result={**upload_result, "source_library_file_id": library_file_id},
        file_info=sliced_file_info,
        library_file_id=sliced_file_id,
        source_type=provider,
        source_url=result.source,
        download_url=download_url,
        extra_metadata={
            "source_library_file_id": str(library_file_id),
            "slice_job_id": str(slice_job_id) if slice_job_id is not None else None,
        },
    )


def _coerce_result(selected: ModelSearchResult | Mapping[str, Any]) -> ModelSearchResult:
    if isinstance(selected, ModelSearchResult):
        return selected
    return ModelSearchResult(**dict(selected))


def _public_import_provider(result: ModelSearchResult) -> str | None:
    if _looks_like_makerworld(result):
        return "makerworld"
    haystack = _provider_haystack(result)
    if "printables" in haystack:
        return "printables"
    if "thingiverse" in haystack:
        return "thingiverse"
    return None


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
    haystack = _provider_haystack(result)
    return "makerworld" in haystack or re.search(r"\bmw\d+\b", haystack) is not None


def _provider_haystack(result: ModelSearchResult) -> str:
    values: list[Any] = [
        result.provider,
        result.source,
        result.result_id,
        result.metadata.get("origin_site"),
        result.metadata.get("source_type"),
        result.metadata.get("source_url"),
        result.metadata.get("download_url"),
        result.metadata.get("file_url"),
    ]
    raw = result.metadata.get("raw")
    if isinstance(raw, Mapping):
        values.extend(
            (
                raw.get("provider"),
                raw.get("origin_site"),
                raw.get("source"),
                raw.get("source_url"),
                raw.get("url"),
            )
        )
    return " ".join(str(value or "") for value in values).casefold()


def _trusted_download_url(result: ModelSearchResult, provider: str) -> str:
    for value in _candidate_download_url_values(result):
        url = str(value or "").strip()
        if not url:
            continue
        if _is_trusted_download_url(url, provider):
            return url
    label = _PROVIDER_LABELS[provider]
    raise UnsupportedPublicImportError(
        f"{label} import requires a trusted {label} direct file URL in candidate "
        "metadata."
    )


def _candidate_download_url_values(result: ModelSearchResult) -> Iterable[Any]:
    if _looks_like_file_url(result.source):
        yield result.source
    yield from _download_url_values(result.metadata)
    raw = result.metadata.get("raw")
    if isinstance(raw, Mapping):
        yield from _download_url_values(raw)


def _download_url_values(value: Any) -> Iterable[Any]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized_key = str(key).replace("-", "_").casefold()
            if normalized_key in _DIRECT_URL_KEYS:
                yield item
            elif normalized_key in {"file", "files", "model_file", "model_files"}:
                yield from _download_url_values(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _download_url_values(item)


def _is_trusted_download_url(url: str, provider: str) -> bool:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or not host:
        return False
    return any(
        host == domain or host.endswith(f".{domain}")
        for domain in _TRUSTED_DOWNLOAD_DOMAINS[provider]
    )


def _looks_like_file_url(value: Any) -> bool:
    parsed = urlsplit(str(value or ""))
    filename = _filename_from_url(str(value or ""))
    return parsed.scheme in {"http", "https"} and bool(filename and "." in filename)


def _metadata_filename(result: ModelSearchResult) -> str | None:
    if result.file_name:
        return str(result.file_name)
    filename = _first_filename(result.metadata)
    if filename:
        return filename
    raw = result.metadata.get("raw")
    if isinstance(raw, Mapping):
        return _first_filename(raw)
    return None


def _first_filename(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized_key = str(key).replace("-", "_").casefold()
            if normalized_key in _FILENAME_KEYS and item:
                return str(item)
            if normalized_key in {"file", "files", "model_file", "model_files"}:
                nested = _first_filename(item)
                if nested:
                    return nested
    elif isinstance(value, list | tuple):
        for item in value:
            nested = _first_filename(item)
            if nested:
                return nested
    return None


def _download_public_file(url: str, *, provider: str) -> DownloadedPublicFile:
    max_bytes = _public_import_max_bytes()
    headers = {"User-Agent": "print-concierge/0.1 (+https://github.com/)"}
    current_url = url
    try:
        with httpx.Client(timeout=30.0, headers=headers, follow_redirects=False) as client:
            for _ in range(6):
                if not _is_trusted_download_url(current_url, provider):
                    raise UnsupportedPublicImportError(
                        f"{_PROVIDER_LABELS[provider]} download redirected outside its "
                        "trusted provider domain."
                    )
                response = client.get(current_url)
                if response.is_redirect:
                    location = response.headers.get("Location")
                    if not location:
                        raise ValueError("public file download redirect was missing Location")
                    current_url = urljoin(str(response.url), location)
                    continue
                response.raise_for_status()
                content = _bounded_response_content(response, max_bytes=max_bytes)
                return DownloadedPublicFile(
                    content=content,
                    filename=_filename_from_content_disposition(response)
                    or _filename_from_url(current_url),
                )
    except httpx.HTTPError as exc:
        raise ValueError(f"public file download failed: {exc.__class__.__name__}") from exc
    raise ValueError("public file download followed too many redirects")


def _bounded_response_content(response: httpx.Response, *, max_bytes: int) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length and int(content_length) > max_bytes:
        raise ValueError("public file download is larger than the configured limit")
    chunks = bytearray()
    for chunk in response.iter_bytes():
        chunks.extend(chunk)
        if len(chunks) > max_bytes:
            raise ValueError("public file download is larger than the configured limit")
    return bytes(chunks)


def _public_import_max_bytes() -> int:
    raw = os.environ.get("PRINT_CONCIERGE_PUBLIC_IMPORT_MAX_BYTES", "157286400")
    try:
        value = int(raw)
    except ValueError:
        return 157286400
    return max(1, value)


def _coerce_downloaded(
    value: DownloadedPublicFile | tuple[bytes, str | None] | bytes,
) -> DownloadedPublicFile:
    if isinstance(value, DownloadedPublicFile):
        if not isinstance(value.content, bytes):
            raise TypeError("public file downloader must return bytes or DownloadedPublicFile")
        return value
    if isinstance(value, bytes):
        return DownloadedPublicFile(content=value)
    if isinstance(value, tuple) and value:
        content = value[0]
        filename = value[1] if len(value) > 1 else None
        if isinstance(content, bytes):
            return DownloadedPublicFile(
                content=content,
                filename=str(filename) if filename else None,
            )
    raise TypeError("public file downloader must return bytes or DownloadedPublicFile")


def _normalize_slice_options(
    slice_options: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if slice_options is None:
        return None
    if not isinstance(slice_options, Mapping):
        raise TypeError("slice_options must be a mapping")
    unknown = sorted(
        str(key) for key in slice_options if key not in _ALLOWED_SLICE_OPTION_KEYS
    )
    if unknown:
        raise ValueError(f"Unsupported slice option: {unknown[0]}")
    payload = {key: value for key, value in slice_options.items() if value is not None}
    if not payload:
        raise ValueError("slice_options must not be empty")
    payload.setdefault("export_3mf", True)
    return payload


def _slice_uploaded_public_file(
    client: Any,
    *,
    source_library_file_id: str,
    slice_options: Mapping[str, Any],
    wait_seconds: float | None,
) -> tuple[Any, Any | None]:
    if not hasattr(client, "slice_library_file") or not hasattr(client, "get_slice_job"):
        raise TypeError("source public import requires Bambuddy slicing methods")
    slice_result = dict(client.slice_library_file(source_library_file_id, slice_options))
    output_file_id = _slice_job_output_file_id(slice_result)
    slice_job_id = _slice_job_id(slice_result)
    if output_file_id is not None:
        return output_file_id, slice_job_id
    if slice_job_id is None:
        raise ValueError("slice response did not include a job id or output file id")

    deadline = time.monotonic() + _slice_wait_seconds(wait_seconds)
    last_job: Mapping[str, Any] = {}
    while True:
        last_job = dict(client.get_slice_job(str(slice_job_id)))
        output_file_id = _slice_job_output_file_id(last_job)
        if output_file_id is not None:
            return output_file_id, slice_job_id
        status = str(last_job.get("status") or "").casefold()
        if status in {"failed", "error", "cancelled", "canceled"}:
            raise ValueError(f"public source slice job failed with status {status}")
        if status in {"completed", "complete", "succeeded", "success", "done"}:
            raise ValueError("completed public source slice job did not include an output file id")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PublicImportNeedsSlicingError(
                "public source slice job has not completed yet; try import again after it finishes."
            )
        time.sleep(min(2.0, remaining))


def _slice_wait_seconds(value: float | None) -> float:
    if value is not None:
        return max(0.0, float(value))
    raw = os.environ.get("PRINT_CONCIERGE_PUBLIC_IMPORT_SLICE_WAIT_SECONDS", "300")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 300.0


def _slice_job_id(value: Mapping[str, Any]) -> Any | None:
    for key in ("job_id", "id", "slice_job_id"):
        if value.get(key) is not None:
            return value[key]
    job = value.get("job")
    if isinstance(job, Mapping):
        return _slice_job_id(job)
    return None


def _slice_job_output_file_id(value: Mapping[str, Any]) -> Any | None:
    for key in (
        "library_file_id",
        "sliced_library_file_id",
        "sliced_file_id",
        "output_file_id",
        "result_file_id",
        "file_id",
    ):
        if value.get(key) is not None:
            return value[key]
    for key in ("result", "output", "file", "library_file"):
        nested = value.get(key)
        if isinstance(nested, Mapping):
            found = _slice_job_output_file_id(nested)
            if found is not None:
                return found
    return None


def _is_queueable_file_info(file_info: Mapping[str, Any]) -> bool:
    return str(file_info.get("file_type") or "").casefold() in _QUEUEABLE_FILE_TYPES


def _trusted_library_result(
    result: ModelSearchResult,
    *,
    import_result: Mapping[str, Any],
    file_info: Mapping[str, Any],
    library_file_id: Any,
    source_type: str,
    source_url: str | None,
    download_url: str | None = None,
    extra_metadata: Mapping[str, Any] | None = None,
) -> ModelSearchResult:
    file_hash = file_info.get("file_hash") or file_info.get("hash")
    if not file_hash:
        raise ValueError("imported public candidate is missing a file hash")
    file_type = str(file_info.get("file_type") or "").casefold()
    if file_type not in _QUEUEABLE_FILE_TYPES:
        if file_type in _SOURCE_FILE_TYPES:
            raise PublicImportNeedsSlicingError(
                "imported public candidate must be sliced before it can be queued."
            )
        raise ValueError("imported public candidate must be a sliced gcode/gcode.3mf file")

    metadata = file_info.get("metadata") if isinstance(file_info.get("metadata"), Mapping) else {}
    license_name = metadata.get("license") or result.license
    file_name = _safe_filename(
        str(file_info.get("filename") or import_result.get("filename") or result.file_name or "")
    )
    imported_source = metadata.get("source_url") or source_url or result.source
    imported_profile = import_result.get("profile_id") or result.profile

    trusted_metadata = {
        "library_file_id": str(library_file_id),
        "folder_id": str(import_result["folder_id"])
        if import_result.get("folder_id") is not None
        else None,
        "source_type": source_type,
        "file_type": file_info.get("file_type"),
        "file_size": file_info.get("file_size"),
        "was_existing": bool(import_result.get("was_existing", False)),
        "verified": True,
        "public_candidate": result.to_public_dict(),
    }
    if download_url:
        trusted_metadata["download_url"] = download_url
    if extra_metadata:
        trusted_metadata.update(dict(extra_metadata))

    return ModelSearchResult(
        provider="bambuddy_library",
        result_id=f"library:{library_file_id}",
        title=result.title,
        description=result.description,
        license=str(license_name) if license_name else None,
        profile=str(imported_profile) if imported_profile is not None else result.profile,
        source=str(imported_source) if imported_source else None,
        model_id=result.model_id,
        file_name=file_name,
        file_hash=str(file_hash),
        warnings=(),
        metadata=trusted_metadata,
    )


def _filename_from_content_disposition(response: httpx.Response) -> str | None:
    header = response.headers.get("Content-Disposition", "")
    match = re.search(r"filename\*=UTF-8''([^;]+)", header, flags=re.IGNORECASE)
    if match:
        return _safe_filename(unquote(match.group(1).strip().strip('"')))
    match = re.search(r'filename="?([^";]+)"?', header, flags=re.IGNORECASE)
    if match:
        return _safe_filename(unquote(match.group(1).strip()))
    return None


def _filename_from_url(url: str) -> str | None:
    path = urlsplit(str(url)).path
    filename = PurePosixPath(unquote(path)).name
    return _safe_filename(filename) if filename else None


def _trusted_download_filename(url: str) -> str | None:
    filename = _filename_from_url(url)
    if not filename:
        return None
    lowered = filename.casefold()
    if lowered.endswith(_QUEUEABLE_FILENAME_SUFFIXES + _SOURCE_FILENAME_SUFFIXES):
        return filename
    return None


def _safe_filename(filename: str | None) -> str:
    cleaned = PurePosixPath(str(filename or "public-model.gcode.3mf").replace("\x00", "")).name
    cleaned = " ".join(cleaned.split()).strip()
    return cleaned or "public-model.gcode.3mf"


def _is_source_filename(filename: str) -> bool:
    return _safe_filename(filename).casefold().endswith(_SOURCE_FILENAME_SUFFIXES)


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
