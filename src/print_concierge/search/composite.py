from __future__ import annotations

from typing import Any, Iterable, Sequence

from print_concierge.search.base import ModelSearchResult, SearchProvider


class CompositeSearchProvider(SearchProvider):
    provider_name = "composite"

    def __init__(self, providers: Iterable[SearchProvider], *, ignore_errors: bool = True):
        self._providers = tuple(providers)
        self._ignore_errors = ignore_errors

    def search(self, query: str, **kwargs: Any) -> Sequence[ModelSearchResult]:
        limit = kwargs.get("limit")
        seen: set[tuple[str, str]] = set()
        results: list[ModelSearchResult] = []
        for provider in self._providers:
            try:
                provider_results = provider.search(query, **kwargs)
            except Exception:
                if self._ignore_errors:
                    continue
                raise
            for result in provider_results:
                key = (result.provider, result.result_id)
                if key in seen:
                    continue
                seen.add(key)
                results.append(result)
                if limit is not None and len(results) >= int(limit):
                    return tuple(results)
        return tuple(results)
