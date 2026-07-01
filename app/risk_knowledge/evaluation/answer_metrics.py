"""Answer metrics for M2D-13."""

from __future__ import annotations

from app.risk_knowledge.evaluation.schemas import AnswerMetrics, GoldenEvaluationCase
from app.risk_knowledge.service.schemas import RiskKnowledgeAnswer


def calculate_answer_metrics(case: GoldenEvaluationCase, answer: RiskKnowledgeAnswer) -> AnswerMetrics:
    points = case.expected_answer_points
    if not points:
        return AnswerMetrics(expected_points_total=0, matched_points=0, answer_point_recall=1.0, has_unsupported_claim=None)

    normalized_answer = answer.answer.lower()
    matched_points = sum(1 for point in points if point.lower() in normalized_answer)
    return AnswerMetrics(
        expected_points_total=len(points),
        matched_points=matched_points,
        answer_point_recall=matched_points / len(points),
        has_unsupported_claim=None,
    )
