from __future__ import annotations


def test_citation_metrics_require_selected_evidence_mapping() -> None:
    from app.risk_knowledge.evaluation.citation_metrics import calculate_citation_metrics
    from app.risk_knowledge.evaluation.schemas import GoldenEvaluationCase
    from app.risk_knowledge.service.schemas import RenderedCitation
    from tests.risk_knowledge.evaluation.conftest import build_bundle

    bundle = build_bundle()
    case = GoldenEvaluationCase(
        case_id="case",
        query="什么是多头借贷风险？",
        kb_id="risk_domain_knowledge",
        expected_behavior="answer",
        expected_evidence=[],
        expected_answer_points=[],
        expected_citation_refs=[{"chunk_id": "risk_chunk_001"}],
        tags=[],
        difficulty="easy",
    )

    metrics = calculate_citation_metrics(
        case=case,
        rendered_citations=[
            RenderedCitation(
                citation_id="bad_id",
                label="[1]",
                document_id="risk_guide",
                document_title="风险手册",
                version_id="risk_guide_v1",
                chunk_id="risk_chunk_001",
                section_path="风险手册 / 多头借贷",
                page_start=1,
                page_end=1,
            )
        ],
        bundle_citations=bundle.citations,
        selected_evidence=bundle.selected_evidence,
        should_answer=True,
    )

    assert metrics.citation_present is True
    assert metrics.invalid_citation_count == 1
    assert metrics.citation_correct is False
