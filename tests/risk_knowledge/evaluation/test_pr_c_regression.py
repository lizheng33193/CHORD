from __future__ import annotations

from app.risk_knowledge.service.schemas import EvidenceTraceItem


def test_evaluator_tracks_pr_c_route_grounding_and_context_isolation() -> None:
    from app.risk_knowledge.evaluation.evaluator import RiskKnowledgeGoldenEvaluator
    from app.risk_knowledge.evaluation.schemas import GoldenEvaluationCase
    from tests.risk_knowledge.evaluation.conftest import build_answer, build_answer_trace, build_bundle

    case = GoldenEvaluationCase(
        case_id="pr_c_risk_qa_case",
        query="什么是多头借贷风险？",
        kb_id="risk_domain_knowledge",
        expected_behavior="answer",
        expected_route="risk_knowledge_answer",
        expected_grounding_status="grounded",
        expected_refusal=False,
        required_evidence_keywords=["多个平台", "信用风险"],
        forbidden_source_types=["data_knowledge", "sql_examples"],
        min_citation_count=1,
        must_include_warning_codes=[],
        notes="PR-C regression baseline",
    )

    bundle = build_bundle()
    answer = build_answer(should_answer=True, bundle=bundle)
    answer = answer.model_copy(
        update={
            "grounding_status": "grounded",
            "evidence_trace": [
                EvidenceTraceItem(
                    evidence_id="evid_risk_chunk_001",
                    source_type="risk_domain_knowledge",
                    document_id="risk_guide",
                    document_name="风险手册",
                    document_version="risk_guide_v1",
                    section_title="多头借贷",
                    section_path=["风险手册", "多头借贷"],
                    page_start=1,
                    page_end=1,
                    chunk_id="risk_chunk_001",
                    evidence_text="多个平台重复申请借款通常意味着更高信用风险。",
                    score=0.95,
                    used_in_answer=True,
                    citation_label="[1]",
                    warnings=[],
                )
            ],
        }
    )
    trace = build_answer_trace(answer=answer, bundle=bundle)

    report = RiskKnowledgeGoldenEvaluator(executor=lambda _case: trace).evaluate([case])

    result = report.case_results[0]
    assert result.passed is True
    assert result.diagnostics["route_matches"] is True
    assert result.diagnostics["grounding_status_matches"] is True
    assert result.diagnostics["forbidden_source_violation_count"] == 0
    assert result.diagnostics["missing_required_evidence_keywords"] == []
    assert report.summary.context_isolation_pass_rate == 1.0


def test_evaluator_fails_pr_c_case_when_forbidden_source_leaks_into_evidence_trace() -> None:
    from app.risk_knowledge.evaluation.evaluator import RiskKnowledgeGoldenEvaluator
    from app.risk_knowledge.evaluation.schemas import GoldenEvaluationCase
    from tests.risk_knowledge.evaluation.conftest import build_answer, build_answer_trace, build_bundle

    case = GoldenEvaluationCase(
        case_id="pr_c_context_leak",
        query="什么是多头借贷风险？",
        kb_id="risk_domain_knowledge",
        expected_behavior="answer",
        expected_route="risk_knowledge_answer",
        expected_grounding_status="grounded",
        forbidden_source_types=["data_knowledge"],
        min_citation_count=1,
    )

    bundle = build_bundle()
    answer = build_answer(should_answer=True, bundle=bundle)
    answer = answer.model_copy(
        update={
            "grounding_status": "grounded",
            "evidence_trace": [
                EvidenceTraceItem(
                    evidence_id="evid_leak",
                    source_type="data_knowledge",
                    document_id="dq_manual",
                    document_name="Data Manual",
                    document_version="v1",
                    section_title="users",
                    section_path=["users"],
                    page_start=1,
                    page_end=1,
                    chunk_id="data_chunk_001",
                    evidence_text="uid is the primary identifier",
                    score=0.88,
                    used_in_answer=True,
                    citation_label="[1]",
                    warnings=[],
                )
            ],
        }
    )
    trace = build_answer_trace(answer=answer, bundle=bundle)

    report = RiskKnowledgeGoldenEvaluator(executor=lambda _case: trace).evaluate([case])

    result = report.case_results[0]
    assert result.passed is False
    assert result.diagnostics["forbidden_source_violation_count"] == 1
    assert report.summary.context_isolation_pass_rate == 0.0
