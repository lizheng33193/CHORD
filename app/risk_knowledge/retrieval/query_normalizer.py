"""Query normalization for M2D-10 retrieval."""

from __future__ import annotations

from app.risk_knowledge.retrieval.errors import InvalidRetrievalQueryError


class QueryNormalizer:
    def __init__(self, *, max_query_chars: int) -> None:
        self._max_query_chars = max_query_chars

    def normalize(self, query: str) -> str:
        normalized = query.strip().lower()
        if not normalized:
            raise InvalidRetrievalQueryError("query must not be empty")
        if len(normalized) > self._max_query_chars:
            raise InvalidRetrievalQueryError(
                f"query length exceeds configured max chars: {self._max_query_chars}"
            )
        return normalized
