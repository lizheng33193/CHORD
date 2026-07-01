from __future__ import annotations


def test_regression_decision_is_advisory() -> None:
    from app.risk_knowledge.evaluation.regression import decide_regression
    from app.risk_knowledge.evaluation.schemas import GoldenEvaluationSummary, RegressionThresholds

    summary = GoldenEvaluationSummary(
        status="completed",
        total_cases=10,
        answer_cases=5,
        refusal_cases=3,
        ambiguous_cases=2,
        retrieval_recall_at_5=0.5,
        retrieval_recall_at_10=0.8,
        retrieval_mrr=0.7,
        rerank_hit_at_3=0.7,
        evidence_precision=0.8,
        evidence_recall=0.8,
        gate_accuracy=0.75,
        refusal_accuracy=1.0,
        false_answer_rate=0.25,
        false_refusal_rate=0.0,
        citation_correctness=0.8,
        answer_point_recall=0.6,
    )

    decision = decide_regression(summary, RegressionThresholds())

    assert decision.advisory is True
    assert decision.passed is False
    assert "min_retrieval_recall_at_5" in decision.failed_thresholds
