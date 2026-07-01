"""Retrieval metrics for M2D-13."""

from __future__ import annotations

from app.risk_knowledge.evaluation.matchers import expected_evidence_matches_candidate
from app.risk_knowledge.evaluation.schemas import GoldenEvaluationCase, RetrievalMetrics
from app.risk_knowledge.retrieval.schemas import HybridRetrievalResult


def calculate_retrieval_metrics(case: GoldenEvaluationCase, retrieval_result: HybridRetrievalResult) -> RetrievalMetrics:
    if not case.expected_evidence:
        return RetrievalMetrics()

    matched_ranks: list[int] = []
    for expected in case.expected_evidence:
        rank = _find_first_matching_rank(expected, retrieval_result)
        if rank is not None:
            matched_ranks.append(rank)

    if not matched_ranks:
        return RetrievalMetrics()

    matched_at_5 = sum(1 for rank in matched_ranks if rank <= 5)
    matched_at_10 = sum(1 for rank in matched_ranks if rank <= 10)
    total_expected = len(case.expected_evidence)
    first_rank = min(matched_ranks)
    return RetrievalMetrics(
        recall_at_5=matched_at_5 / total_expected,
        recall_at_10=matched_at_10 / total_expected,
        mrr=1.0 / first_rank,
        hit_at_5=first_rank <= 5,
        hit_at_10=first_rank <= 10,
    )


def _find_first_matching_rank(expected, retrieval_result: HybridRetrievalResult) -> int | None:
    for index, candidate in enumerate(retrieval_result.candidates, start=1):
        if expected_evidence_matches_candidate(expected, candidate):
            return candidate.fused_rank or index
    return None
