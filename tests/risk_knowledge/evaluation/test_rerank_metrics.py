from __future__ import annotations


def test_rerank_metrics_calculates_uplift() -> None:
    from app.risk_knowledge.evaluation.rerank_metrics import calculate_rerank_metrics
    from app.risk_knowledge.evaluation.schemas import GoldenEvaluationCase
    from tests.risk_knowledge.evaluation.conftest import build_retrieval_result, build_rerank_result

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

    metrics = calculate_rerank_metrics(case, build_retrieval_result(), build_rerank_result())

    assert metrics.rerank_hit_at_1 is True
    assert metrics.rerank_mrr == 1.0
    assert metrics.rerank_uplift == 0.0
