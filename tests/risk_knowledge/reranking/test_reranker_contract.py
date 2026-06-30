from __future__ import annotations

import pytest


def test_deterministic_reranker_rejects_empty_candidates() -> None:
    from app.risk_knowledge.reranking.deterministic_provider import DeterministicRerankerProvider
    from app.risk_knowledge.reranking.errors import InvalidRerankRequestError
    from app.risk_knowledge.reranking.schemas import RerankRequest

    provider = DeterministicRerankerProvider()
    request = RerankRequest(query="loan risk", candidates=[], model="deterministic-rerank-v1")

    with pytest.raises(InvalidRerankRequestError):
        provider.rerank(request)
