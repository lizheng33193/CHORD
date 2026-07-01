"""Rerank metrics for M2D-13."""

from __future__ import annotations

from app.risk_knowledge.evaluation.schemas import GoldenEvaluationCase, RerankMetrics
from app.risk_knowledge.retrieval.schemas import HybridRetrievalResult
from app.risk_knowledge.reranking.schemas import RerankResult


def calculate_rerank_metrics(
    case: GoldenEvaluationCase,
    retrieval_result: HybridRetrievalResult,
    rerank_result: RerankResult | None,
) -> RerankMetrics:
    if not case.expected_evidence or rerank_result is None:
        return RerankMetrics()

    expected_chunk_ids = {expected.chunk_id for expected in case.expected_evidence if expected.chunk_id}
    if not expected_chunk_ids:
        return RerankMetrics()

    rerank_rank = next((item.rerank_rank for item in rerank_result.items if item.chunk_id in expected_chunk_ids), None)
    if rerank_rank is None:
        return RerankMetrics()

    retrieval_rank = next(
        (candidate.fused_rank for candidate in retrieval_result.candidates if candidate.chunk_id in expected_chunk_ids),
        None,
    )
    uplift = None if retrieval_rank is None else float(retrieval_rank - rerank_rank)
    return RerankMetrics(
        rerank_hit_at_1=rerank_rank <= 1,
        rerank_hit_at_3=rerank_rank <= 3,
        rerank_hit_at_5=rerank_rank <= 5,
        rerank_mrr=1.0 / rerank_rank,
        rerank_uplift=uplift,
    )
