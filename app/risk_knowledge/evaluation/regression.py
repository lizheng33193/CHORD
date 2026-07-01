"""Advisory regression decision logic for M2D-13."""

from __future__ import annotations

from app.risk_knowledge.evaluation.schemas import (
    GoldenEvaluationSummary,
    RegressionDecision,
    RegressionThresholds,
)


def decide_regression(
    summary: GoldenEvaluationSummary,
    thresholds: RegressionThresholds,
) -> RegressionDecision:
    failed_thresholds: list[str] = []
    if summary.retrieval_recall_at_5 < thresholds.min_retrieval_recall_at_5:
        failed_thresholds.append("min_retrieval_recall_at_5")
    if summary.retrieval_recall_at_10 < thresholds.min_retrieval_recall_at_10:
        failed_thresholds.append("min_retrieval_recall_at_10")
    if summary.gate_accuracy < thresholds.min_gate_accuracy:
        failed_thresholds.append("min_gate_accuracy")
    if summary.false_answer_rate > thresholds.max_false_answer_rate:
        failed_thresholds.append("max_false_answer_rate")
    if summary.citation_correctness < thresholds.min_citation_correctness:
        failed_thresholds.append("min_citation_correctness")

    passed = not failed_thresholds
    summary_text = "advisory thresholds satisfied" if passed else f"advisory thresholds failed: {', '.join(failed_thresholds)}"
    return RegressionDecision(
        advisory=True,
        passed=passed,
        failed_thresholds=failed_thresholds,
        summary=summary_text,
    )
