"""Deterministic reranker for offline M2D-11 tests."""

from __future__ import annotations

from app.risk_knowledge.reranking.errors import InvalidRerankRequestError
from app.risk_knowledge.reranking.schemas import RerankItem, RerankRequest, RerankResult


class DeterministicRerankerProvider:
    provider_name = "deterministic"

    def rerank(self, request: RerankRequest) -> RerankResult:
        if not request.candidates:
            raise InvalidRerankRequestError("rerank candidates must not be empty")

        ranked_candidates = sorted(
            enumerate(request.candidates),
            key=lambda item: (-len(item[1].text), item[1].candidate_id),
        )
        if request.top_n is not None:
            ranked_candidates = ranked_candidates[: request.top_n]

        items = [
            RerankItem(
                candidate_index=index,
                candidate_id=candidate.candidate_id,
                chunk_id=candidate.chunk_id,
                rerank_score=float(len(candidate.text)),
                rerank_rank=rank,
            )
            for rank, (index, candidate) in enumerate(ranked_candidates, start=1)
        ]
        return RerankResult(provider=self.provider_name, model=request.model, items=items)
