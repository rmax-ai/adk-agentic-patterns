"""Mock document/vector store with deterministic similarity and citation support."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Document:
    doc_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    access_tags: list[str] = field(default_factory=list)


@dataclass
class SearchResult:
    doc_id: str
    content: str
    score: float
    citation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class MockDocumentStore:
    """In-memory document store with deterministic keyword/hybrid retrieval.

    Supports insert, retrieve, metadata filtering, deterministic similarity
    scoring, citation IDs, poisoned-document fixtures, and access-control tags.
    """

    def __init__(self) -> None:
        self._docs: dict[str, Document] = {}
        self._scores: dict[str, dict[str, float]] = {}  # query → {doc_id: score}

    def insert(self, doc: Document) -> None:
        self._docs[doc.doc_id] = doc

    def get(self, doc_id: str) -> Document | None:
        return self._docs.get(doc_id)

    def set_scores(self, query: str, scores: dict[str, float]) -> None:
        """Predefine similarity scores for a query (deterministic testing)."""
        self._scores[query] = scores

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0,
        access_tags: list[str] | None = None,
    ) -> list[SearchResult]:
        """Search with predefined or keyword-based scoring."""
        if query in self._scores:
            scored = self._scores[query]
        else:
            # Fallback: simple keyword match scoring
            scored = {}
            query_lower = query.lower()
            for doc_id, doc in self._docs.items():
                score = sum(1 for word in query_lower.split() if word in doc.content.lower())
                if score > 0:
                    scored[doc_id] = min(score / max(len(query_lower.split()), 1), 1.0)

        results = []
        for doc_id, score in sorted(scored.items(), key=lambda x: -x[1]):
            doc = self._docs.get(doc_id)
            if not doc or score < min_score:
                continue
            if access_tags and not any(t in doc.access_tags for t in access_tags):
                continue
            results.append(SearchResult(
                doc_id=doc_id,
                content=doc.content,
                score=score,
                citation_id=f"cite:{doc_id}",
                metadata=doc.metadata,
            ))
            if len(results) >= top_k:
                break

        return results

    def reset(self) -> None:
        self._docs.clear()
        self._scores.clear()
