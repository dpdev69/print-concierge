from __future__ import annotations

import json
import os
from html import unescape
from html.parser import HTMLParser
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qsl, quote_plus, unquote, urlencode, urlsplit, urlunsplit

import httpx

from print_concierge.search.base import ModelSearchResult, SearchProvider, normalize_result

MODEL_SITE_DOMAINS = {
    "makerworld": "makerworld.com",
    "printables": "printables.com",
    "thingiverse": "thingiverse.com",
    "thangs": "thangs.com",
}


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


class PublicModelSiteSearchProvider(SearchProvider):
    provider_name = "public_model_web"

    def __init__(
        self,
        *,
        sites: Sequence[str] = ("makerworld", "printables", "thingiverse", "thangs"),
        search_url_template: str = "https://duckduckgo.com/html/?q={query}",
        http_client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._sites = tuple(sites)
        self._search_url_template = search_url_template
        self._client = http_client or httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "print-concierge/0.1 (+https://github.com/)"},
            follow_redirects=True,
        )

    def search(self, query: str, **kwargs: Any) -> Sequence[ModelSearchResult]:
        limit = int(kwargs.get("limit") or 5)
        results: list[ModelSearchResult] = []
        seen: set[str] = set()
        for site in self._sites:
            domain = MODEL_SITE_DOMAINS.get(site, site)
            search_query = f'site:{domain} "{query}"'
            response = self._client.get(
                self._search_url_template.format(query=quote_plus(search_query))
            )
            response.raise_for_status()
            parsed = _SearchResultParser().parse(response.text)
            for item in parsed:
                source = _clean_search_url(item["url"])
                if not source or source in seen or not _matches_domain(source, domain):
                    continue
                seen.add(source)
                result = normalize_result(
                    f"{site}_web",
                    {
                        "result_id": source,
                        "title": item["title"],
                        "description": item.get("snippet", ""),
                        "source": source,
                    },
                )
                warnings = tuple(
                    dict.fromkeys((*result.warnings, "missing_file_hash"))
                )
                results.append(
                    ModelSearchResult(
                        **{**result.to_dict(), "warnings": warnings}
                    )
                )
                if len(results) >= limit:
                    return tuple(results)
        return tuple(results)


class ThreeDSearchProvider(SearchProvider):
    provider_name = "3dsearch"

    def __init__(
        self,
        *,
        search_url_template: str = "https://3dsearch.net/?q={query}&lang=en",
        http_client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._search_url_template = search_url_template
        self._client = http_client or httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "print-concierge/0.1 (+https://github.com/)"},
            follow_redirects=True,
        )

    def search(self, query: str, **kwargs: Any) -> Sequence[ModelSearchResult]:
        limit = int(kwargs.get("limit") or 5)
        url = self._search_url_template.format(query=quote_plus(query))
        response = self._client.get(url)
        response.raise_for_status()
        parsed = _ThreeDSearchParser().parse(response.text)
        results: list[ModelSearchResult] = []
        seen: set[str] = set()
        for item in parsed:
            source = _absolute_url(url, item["href"])
            if not source or source in seen:
                continue
            seen.add(source)
            origin_site = item.get("origin_site") or "3DSEARCH"
            provider = f"3dsearch_{_slug(origin_site)}"
            results.append(
                ModelSearchResult(
                    provider=provider,
                    result_id=source,
                    title=item["title"],
                    description=f"Aggregated from {origin_site}",
                    source=source,
                    warnings=(
                        "missing_license",
                        "missing_profile",
                        "missing_file_hash",
                    ),
                    metadata={
                        "aggregator": "3dsearch",
                        "origin_site": origin_site,
                    },
                )
            )
            if len(results) >= limit:
                return tuple(results)
        return tuple(results)


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


def default_public_search_provider(
    environ: Mapping[str, str] | None = None,
    *,
    http_client: httpx.Client | None = None,
) -> PublicModelSiteSearchProvider | None:
    env = environ or os.environ
    enabled = env.get("PRINT_CONCIERGE_PUBLIC_WEB_SEARCH_ENABLED", "true").lower()
    if enabled in {"0", "false", "no", "off"}:
        return None
    backend = env.get("PRINT_CONCIERGE_PUBLIC_WEB_SEARCH_BACKEND", "3dsearch").lower()
    if backend in {"3dsearch", "3dsearch.net"}:
        return ThreeDSearchProvider(
            search_url_template=env.get(
                "PRINT_CONCIERGE_3DSEARCH_SEARCH_URL",
                "https://3dsearch.net/?q={query}&lang=en",
            ),
            http_client=http_client,
        )
    sites = tuple(
        site.strip()
        for site in env.get(
            "PRINT_CONCIERGE_PUBLIC_WEB_SEARCH_SITES",
            "makerworld,printables,thingiverse,thangs",
        ).split(",")
        if site.strip()
    )
    return PublicModelSiteSearchProvider(
        sites=sites,
        search_url_template=env.get(
            "PRINT_CONCIERGE_PUBLIC_WEB_SEARCH_URL",
            "https://duckduckgo.com/html/?q={query}",
        ),
        http_client=http_client,
    )


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


class _SearchResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._capture: str | None = None
        self._current_href: str | None = None
        self._current_text: list[str] = []
        self._last_result: dict[str, str] | None = None
        self.results: list[dict[str, str]] = []

    def parse(self, html: str) -> list[dict[str, str]]:
        self.feed(html)
        return self.results

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        classes = set(attr_map.get("class", "").split())
        if tag == "a" and "result__a" in classes:
            self._capture = "title"
            self._current_href = attr_map.get("href", "")
            self._current_text = []
        elif tag in {"a", "div"} and "result__snippet" in classes:
            self._capture = "snippet"
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capture == "title" and tag == "a":
            text = " ".join("".join(self._current_text).split())
            if text and self._current_href:
                self._last_result = {
                    "title": unescape(text),
                    "url": self._current_href,
                }
                self.results.append(self._last_result)
            self._reset_capture()
        elif self._capture == "snippet" and tag in {"a", "div"}:
            text = " ".join("".join(self._current_text).split())
            if text and self._last_result is not None:
                self._last_result["snippet"] = unescape(text)
            self._reset_capture()

    def _reset_capture(self) -> None:
        self._capture = None
        self._current_href = None
        self._current_text = []


class _ThreeDSearchParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._current: dict[str, str] | None = None
        self._capture: str | None = None
        self._current_text: list[str] = []
        self.results: list[dict[str, str]] = []

    def parse(self, html: str) -> list[dict[str, str]]:
        self.feed(html)
        return self.results

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        classes = set(attr_map.get("class", "").split())
        if tag == "a" and "card-link" in classes:
            self._current = {
                "href": attr_map.get("href", ""),
                "title": unescape(attr_map.get("title", "")),
            }
        elif self._current is not None and tag == "span" and "card-source" in classes:
            self._capture = "origin_site"
            self._current_text = []
        elif self._current is not None and tag == "div" and "card-title" in classes:
            self._capture = "title"
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capture and tag in {"span", "div"}:
            text = " ".join("".join(self._current_text).split())
            if text and self._current is not None:
                self._current[self._capture] = unescape(text)
            self._capture = None
            self._current_text = []
        if tag == "a" and self._current is not None:
            if self._current.get("href") and self._current.get("title"):
                self.results.append(dict(self._current))
            self._current = None


def _clean_search_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    if url.startswith("/l/"):
        url = "https://duckduckgo.com" + url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if "uddg" in query:
        return unquote(query["uddg"])
    if parts.scheme and parts.netloc:
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
    return ""


def _matches_domain(url: str, domain: str) -> bool:
    host = urlsplit(url).netloc.lower()
    return host == domain or host.endswith(f".{domain}")


def _absolute_url(base_url: str, href: str) -> str:
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    parts = urlsplit(base_url)
    if href.startswith("/"):
        return urlunsplit((parts.scheme, parts.netloc, href, "", ""))
    prefix = parts.path.rsplit("/", 1)[0]
    return urlunsplit((parts.scheme, parts.netloc, f"{prefix}/{href}", "", ""))


def _slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_") or "unknown"


def _with_query_param(url: str, key: str, value: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[key] = value
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
