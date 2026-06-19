"""Mock Vector Store — lightweight in-memory vector store with deterministic similarity.

Used by the Agentic RAG pattern for local document retrieval with embeddings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VectorDocument:
    doc_id: str
    content: str
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VectorSearchResult:
    doc_id: str
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class MockVectorStore:
    """In-memory vector store with deterministic similarity scoring."""

    def __init__(self) -> None:
        self._docs: dict[str, VectorDocument] = {}
        self._scores: dict[str, dict[str, float]] = {}  # query → {doc_id: score}
        self._poisoned: set[str] = set()

    def insert(self, doc: VectorDocument) -> None:
        self._docs[doc.doc_id] = doc

    def set_scores(self, query: str, scores: dict[str, float]) -> None:
        self._scores[query] = scores

    def add_poisoned(self, doc_id: str) -> None:
        self._poisoned.add(doc_id)

    def search(self, query: str, top_k: int = 5, min_score: float = 0.0) -> list[VectorSearchResult]:
        if query in self._scores:
            scored = self._scores[query]
        else:
            # Fallback: keyword match
            scored = {}
            query_lower = query.lower()
            for doc_id, doc in self._docs.items():
                if doc_id in self._poisoned:
                    continue
                words_in_common = sum(1 for w in query_lower.split() if w in doc.content.lower())
                if words_in_common > 0:
                    scored[doc_id] = words_in_common / max(len(query_lower.split()), 1)

        results = []
        for doc_id, score in sorted(scored.items(), key=lambda x: -x[1]):
            if score < min_score:
                continue
            doc = self._docs.get(doc_id)
            if not doc:
                continue
            results.append(VectorSearchResult(
                doc_id=doc_id,
                content=doc.content,
                score=score,
                metadata=doc.metadata,
            ))
            if len(results) >= top_k:
                break
        return results

    def reset(self) -> None:
        self._docs.clear()
        self._scores.clear()
        self._poisoned.clear()
