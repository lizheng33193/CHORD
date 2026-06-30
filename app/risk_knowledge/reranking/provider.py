"""Provider protocol for M2D-11 reranking."""

from __future__ import annotations

from typing import Protocol

from app.risk_knowledge.reranking.schemas import RerankRequest, RerankResult


class RerankerProvider(Protocol):
    provider_name: str

    def rerank(self, request: RerankRequest) -> RerankResult:
        """Return rerank results for a non-empty candidate list."""
