from __future__ import annotations


def test_evidence_metrics_calculates_precision_and_recall() -> None:
    from app.risk_knowledge.evaluation.evidence_metrics import calculate_evidence_selection_metrics
    from app.risk_knowledge.evaluation.schemas import GoldenEvaluationCase
    from tests.risk_knowledge.evaluation.conftest import build_bundle

    case = GoldenEvaluationCase(
        case_id="case",
        query="什么是多头借贷风险？",
        kb_id="risk_domain_knowledge",
        expected_behavior="answer",
        expected_evidence=[{"chunk_id": "risk_chunk_001", "text_contains": ["多个平台"]}],
        expected_answer_points=[],
        expected_citation_refs=[],
        tags=[],
        difficulty="easy",
    )

    metrics = calculate_evidence_selection_metrics(case, build_bundle())

    assert metrics.selected_expected_evidence is True
    assert metrics.selected_count == 1
    assert metrics.evidence_precision == 1.0
    assert metrics.evidence_recall == 1.0
