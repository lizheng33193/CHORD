from __future__ import annotations


def test_answer_metrics_use_lexical_point_matching_only() -> None:
    from app.risk_knowledge.evaluation.answer_metrics import calculate_answer_metrics
    from app.risk_knowledge.evaluation.schemas import GoldenEvaluationCase
    from tests.risk_knowledge.evaluation.conftest import build_answer

    case = GoldenEvaluationCase(
        case_id="case",
        query="什么是多头借贷风险？",
        kb_id="risk_domain_knowledge",
        expected_behavior="answer",
        expected_evidence=[],
        expected_answer_points=["多个平台", "信用风险", "不存在的点"],
        expected_citation_refs=[],
        tags=[],
        difficulty="easy",
    )

    metrics = calculate_answer_metrics(case, build_answer())

    assert metrics.expected_points_total == 3
    assert metrics.matched_points == 2
    assert metrics.answer_point_recall == 2 / 3
    assert metrics.has_unsupported_claim is None
