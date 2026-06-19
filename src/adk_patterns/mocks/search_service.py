"""Mock search service with deterministic ranking, latency simulation, and error injection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchHit:
    id: str
    title: str
    snippet: str
    score: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


class MockSearchService:
    """Mock search service for offline testing.

    Supports deterministic result ranking, query history, latency simulation,
    empty result sets, timeouts, and stale result fixtures.
    """

    def __init__(self) -> None:
        self._index: dict[str, list[SearchHit]] = {}  # query → results
        self._query_history: list[str] = []
        self._timeout: bool = False
        self._empty: bool = False
        self._error: Exception | None = None

    def index(self, query: str, hits: list[SearchHit]) -> None:
        self._index[query] = hits

    def search(self, query: str, top_k: int = 5) -> list[SearchHit]:
        if self._error:
            raise self._error
        if self._timeout:
            self._timeout = False
            raise TimeoutError(f"Search timed out for query: {query}")
        self._query_history.append(query)
        if self._empty:
            return []
        hits = self._index.get(query, [])
        return hits[:top_k]

    def set_timeout(self) -> None:
        self._timeout = True

    def set_empty(self) -> None:
        self._empty = True

    def set_error(self, error: Exception) -> None:
        self._error = error

    @property
    def query_history(self) -> list[str]:
        return list(self._query_history)

    def reset(self) -> None:
        self._index.clear()
        self._query_history.clear()
        self._timeout = False
        self._empty = False
        self._error = None
