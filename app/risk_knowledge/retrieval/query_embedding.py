"""Query embedding service for M2D-10 retrieval."""

from __future__ import annotations

from app.risk_knowledge.embedding.base import EmbeddingProvider
from app.risk_knowledge.embedding.errors import (
    EmbeddingDimensionMismatchError,
    EmbeddingProviderError,
)
from app.risk_knowledge.embedding.schemas import EmbeddingInput
from app.risk_knowledge.retrieval.errors import (
    QueryEmbeddingDimensionMismatchError,
    QueryEmbeddingProviderError,
)
from app.risk_knowledge.retrieval.schemas import QueryEmbeddingResult


class QueryEmbeddingService:
    def __init__(self, *, provider: EmbeddingProvider, expected_dimension: int) -> None:
        self._provider = provider
        self._expected_dimension = expected_dimension

    def embed_query(self, query: str) -> QueryEmbeddingResult:
        try:
            records = self._provider.embed(
                [
                    EmbeddingInput(
                        chunk_id="__query__",
                        content_hash="sha256:query",
                        text=query,
                        input_type="query",
                    )
                ]
            )
        except EmbeddingDimensionMismatchError as exc:
            raise QueryEmbeddingDimensionMismatchError(str(exc)) from exc
        except EmbeddingProviderError as exc:
            raise QueryEmbeddingProviderError(str(exc)) from exc
        except Exception as exc:  # pylint: disable=broad-except
            raise QueryEmbeddingProviderError(str(exc)) from exc

        if len(records) != 1:
            raise QueryEmbeddingProviderError("query embedding provider returned unexpected batch size")
        record = records[0]
        if record.dimension != self._expected_dimension:
            raise QueryEmbeddingDimensionMismatchError(
                f"expected dimension {self._expected_dimension}, got {record.dimension}"
            )
        return QueryEmbeddingResult(
            provider=record.provider,
            model=record.model,
            dimension=record.dimension,
            vector=list(record.vector),
            vector_checksum=record.vector_checksum,
        )
