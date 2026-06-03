import json

import httpx

from print_concierge.search.base import ModelSearchResult
from print_concierge.search.composite import CompositeSearchProvider
from print_concierge.search.external import (
    ConfiguredExternalSearchProvider,
    HttpJsonSearchProvider,
    MakerWorldSearchProvider,
    PublicModelSiteSearchProvider,
    ThreeDSearchProvider,
    configured_external_providers,
    default_public_search_provider,
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


def test_public_model_site_search_provider_parses_search_results():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(
            200,
            content="""
            <html>
              <body>
                <a class="result__a" href="/l/?uddg=https%3A%2F%2Fmakerworld.com%2Fen%2Fmodels%2F1282635">
                  Universal cable holder V2
                </a>
                <a class="result__snippet">A printable cable holder for desks.</a>
                <a class="result__a" href="https://makerworld.com/en/models/9999-cable-clip">
                  Cable clip by MakerWorld user
                </a>
              </body>
            </html>
            """,
        )

    provider = PublicModelSiteSearchProvider(
        sites=("makerworld",),
        search_url_template="https://search.example/html/?q={query}",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    results = provider.search("cable holder", limit=2)

    assert seen == [
        "https://search.example/html/?q=site%3Amakerworld.com+%22cable+holder%22"
    ]
    assert [(result.provider, result.title, result.source) for result in results] == [
        (
            "makerworld_web",
            "Universal cable holder V2",
            "https://makerworld.com/en/models/1282635",
        ),
        (
            "makerworld_web",
            "Cable clip by MakerWorld user",
            "https://makerworld.com/en/models/9999-cable-clip",
        ),
    ]
    assert results[0].warnings == (
        "missing_license",
        "missing_profile",
        "missing_file_hash",
    )


def test_threedsearch_provider_parses_model_cards():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(
            200,
            content="""
            <div class="model-card">
              <a href="/model/universal-cable-holder-mw1282635" class="card-link" title="Universal cable holder">
                <span class="card-source makerworld">MakerWorld</span>
                <div class="card-title">Universal cable holder</div>
              </a>
            </div>
            <div class="model-card">
              <a href="/model/gridfinity-bin-pr123" class="card-link" title="Gridfinity bin">
                <span class="card-source printables">Printables</span>
                <div class="card-title">Gridfinity bin</div>
              </a>
            </div>
            """,
        )

    provider = ThreeDSearchProvider(
        search_url_template="https://3dsearch.example/?q={query}&lang=en",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    results = provider.search("cable holder", limit=2)

    assert seen == ["https://3dsearch.example/?q=cable+holder&lang=en"]
    assert [(result.provider, result.title, result.source) for result in results] == [
        (
            "3dsearch_makerworld",
            "Universal cable holder",
            "https://3dsearch.example/model/universal-cable-holder-mw1282635",
        ),
        (
            "3dsearch_printables",
            "Gridfinity bin",
            "https://3dsearch.example/model/gridfinity-bin-pr123",
        ),
    ]
    assert results[0].metadata == {"aggregator": "3dsearch", "origin_site": "MakerWorld"}


def test_default_public_search_provider_uses_3dsearch_by_default(monkeypatch):
    monkeypatch.delenv("PRINT_CONCIERGE_PUBLIC_WEB_SEARCH_ENABLED", raising=False)
    monkeypatch.delenv("PRINT_CONCIERGE_PUBLIC_WEB_SEARCH_BACKEND", raising=False)

    assert isinstance(default_public_search_provider(), ThreeDSearchProvider)


def test_default_public_search_provider_can_be_disabled(monkeypatch):
    monkeypatch.setenv("PRINT_CONCIERGE_PUBLIC_WEB_SEARCH_ENABLED", "false")

    assert default_public_search_provider() is None
