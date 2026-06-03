from __future__ import annotations

import json
import os
from typing import Any, Mapping, Sequence
from urllib.parse import quote_plus, urlencode, urlsplit, urlunsplit, parse_qsl

import httpx

from print_concierge.search.base import ModelSearchResult, SearchProvider, normalize_result


class HttpJsonSearchProvider(SearchProvider):
    def __init__(
        self,
        *,
        provider_name: str,
        search_url_template: str,
        result_path: str = "results",
        http_client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.provider_name = provider_name
        self._search_url_template = search_url_template
        self._result_path = result_path
        self._client = http_client or httpx.Client(timeout=timeout)

    def search(self, query: str, **kwargs: Any) -> Sequence[ModelSearchResult]:
        limit = kwargs.get("limit")
        url = self._search_url(query=query, limit=limit)
        response = self._client.get(url)
        response.raise_for_status()
        records = self._records(response.json())
        if limit is not None:
            records = records[: int(limit)]
        return tuple(normalize_result(self.provider_name, record) for record in records)

    def _search_url(self, *, query: str, limit: Any = None) -> str:
        encoded_query = quote_plus(query)
        format_values = {"query": encoded_query, "limit": "" if limit is None else str(limit)}
        url = self._search_url_template.format(**format_values)
        if limit is None or "{limit}" in self._search_url_template:
            return url
        return _with_query_param(url, "limit", str(limit))

    def _records(self, payload: Any) -> list[Mapping[str, Any]]:
        value = payload
        if self._result_path:
            for part in self._result_path.split("."):
                if isinstance(value, Mapping):
                    value = value.get(part, [])
                else:
                    value = []
                    break
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
        if isinstance(value, Mapping):
            return [value]
        return []


class MakerWorldSearchProvider(HttpJsonSearchProvider):
    def __init__(self, search_url_template: str, **kwargs: Any) -> None:
        super().__init__(
            provider_name="makerworld",
            search_url_template=search_url_template,
            **kwargs,
        )


class PrintablesSearchProvider(HttpJsonSearchProvider):
    def __init__(self, search_url_template: str, **kwargs: Any) -> None:
        super().__init__(
            provider_name="printables",
            search_url_template=search_url_template,
            **kwargs,
        )


class ConfiguredExternalSearchProvider(HttpJsonSearchProvider):
    def __init__(
        self,
        config: Mapping[str, Any],
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        provider_name = str(config.get("name") or config.get("provider") or "external")
        search_url_template = str(
            config.get("url") or config.get("search_url_template") or ""
        )
        if not search_url_template:
            raise ValueError("external search provider config requires url")
        super().__init__(
            provider_name=provider_name,
            search_url_template=search_url_template,
            result_path=str(config.get("result_path") or "results"),
            http_client=http_client,
        )


def configured_external_providers(
    environ: Mapping[str, str] | None = None,
    *,
    http_client: httpx.Client | None = None,
) -> list[SearchProvider]:
    env = environ or os.environ
    providers: list[SearchProvider] = []
    makerworld_url = env.get("PRINT_CONCIERGE_MAKERWORLD_SEARCH_URL")
    if makerworld_url:
        providers.append(
            MakerWorldSearchProvider(makerworld_url, http_client=http_client)
        )
    printables_url = env.get("PRINT_CONCIERGE_PRINTABLES_SEARCH_URL")
    if printables_url:
        providers.append(
            PrintablesSearchProvider(printables_url, http_client=http_client)
        )
    for config in _external_provider_configs(env):
        providers.append(
            ConfiguredExternalSearchProvider(config, http_client=http_client)
        )
    return providers


def _external_provider_configs(env: Mapping[str, str]) -> list[Mapping[str, Any]]:
    raw = env.get("PRINT_CONCIERGE_EXTERNAL_SEARCH_PROVIDERS", "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        nested = payload.get("providers")
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, Mapping)]
    return []


def _with_query_param(url: str, key: str, value: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[key] = value
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
