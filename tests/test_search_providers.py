import json

import httpx

from print_concierge.search.base import ModelSearchResult
from print_concierge.search.composite import CompositeSearchProvider
from print_concierge.search.external import (
    ConfiguredExternalSearchProvider,
    HttpJsonSearchProvider,
    MakerWorldSearchProvider,
    configured_external_providers,
)


def test_http_json_search_provider_normalizes_results_and_encodes_query():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "mw-1",
                        "title": "Desk cable clip",
                        "license": "CC-BY",
                        "profile": "0.20mm",
                        "url": "https://makerworld.example/model/mw-1",
                        "file": {"name": "clip.3mf", "sha256": "abc123"},
                    }
                ]
            },
        )

    provider = HttpJsonSearchProvider(
        provider_name="makerworld",
        search_url_template="https://search.example/models?q={query}",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    results = provider.search("desk cable", limit=5)

    assert seen["url"] == "https://search.example/models?q=desk+cable&limit=5"
    assert results == (
        ModelSearchResult(
            provider="makerworld",
            result_id="mw-1",
            title="Desk cable clip",
            license="CC-BY",
            profile="0.20mm",
            source="https://makerworld.example/model/mw-1",
            file_name="clip.3mf",
            file_hash="abc123",
            metadata={
                "raw": {
                    "id": "mw-1",
                    "title": "Desk cable clip",
                    "license": "CC-BY",
                    "profile": "0.20mm",
                    "url": "https://makerworld.example/model/mw-1",
                    "file": {"name": "clip.3mf", "sha256": "abc123"},
                }
            },
        ),
    )


def test_composite_search_provider_dedupes_and_limits_results():
    class Provider:
        def __init__(self, provider_name, titles):
            self.provider_name = provider_name
            self._titles = titles

        def search(self, query, **kwargs):
            return tuple(
                ModelSearchResult(
                    provider=self.provider_name,
                    result_id=result_id,
                    title=title,
                    source=f"https://example.test/{result_id}",
                    license="CC0",
                    profile="0.20mm",
                )
                for result_id, title in self._titles
            )

    provider = CompositeSearchProvider(
        [
            Provider("local_archive", [("a1", "Cable clip"), ("a1", "Cable clip duplicate")]),
            Provider("makerworld", [("mw1", "Cable raceway")]),
        ]
    )

    results = provider.search("cable", limit=2)

    assert [(item.provider, item.result_id, item.title) for item in results] == [
        ("local_archive", "a1", "Cable clip"),
        ("makerworld", "mw1", "Cable raceway"),
    ]


def test_configured_external_providers_build_named_provider_adapters(monkeypatch):
    monkeypatch.setenv(
        "PRINT_CONCIERGE_MAKERWORLD_SEARCH_URL",
        "https://search.example/makerworld?q={query}",
    )
    monkeypatch.delenv("PRINT_CONCIERGE_PRINTABLES_SEARCH_URL", raising=False)

    providers = configured_external_providers()

    assert len(providers) == 1
    assert isinstance(providers[0], MakerWorldSearchProvider)
    assert providers[0].provider_name == "makerworld"


def test_configured_external_providers_support_json_provider_configs(monkeypatch):
    monkeypatch.delenv("PRINT_CONCIERGE_MAKERWORLD_SEARCH_URL", raising=False)
    monkeypatch.delenv("PRINT_CONCIERGE_PRINTABLES_SEARCH_URL", raising=False)
    monkeypatch.setenv(
        "PRINT_CONCIERGE_EXTERNAL_SEARCH_PROVIDERS",
        json.dumps(
            [
                {
                    "name": "thangs",
                    "url": "https://search.example/thangs?q={query}",
                    "result_path": "items",
                }
            ]
        ),
    )

    providers = configured_external_providers()

    assert len(providers) == 1
    assert isinstance(providers[0], ConfiguredExternalSearchProvider)
    assert providers[0].provider_name == "thangs"
