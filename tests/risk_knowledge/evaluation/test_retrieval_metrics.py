from __future__ import annotations


def test_retrieval_metrics_calculates_recall_and_mrr() -> None:
    from app.risk_knowledge.evaluation.retrieval_metrics import calculate_retrieval_metrics
    from app.risk_knowledge.evaluation.schemas import GoldenEvaluationCase
    from tests.risk_knowledge.evaluation.conftest import build_retrieval_result

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

    metrics = calculate_retrieval_metrics(case, build_retrieval_result())

    assert metrics.hit_at_5 is True
    assert metrics.hit_at_10 is True
    assert metrics.recall_at_5 == 1.0
    assert metrics.mrr == 1.0
