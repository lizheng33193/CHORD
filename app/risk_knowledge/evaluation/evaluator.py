"""M2D-13 evaluator orchestration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol

from app.knowledge_base.config import DEFAULT_RISK_KB_ID
from app.risk_knowledge.evaluation.answer_metrics import calculate_answer_metrics
from app.risk_knowledge.evaluation.citation_metrics import calculate_citation_metrics
from app.risk_knowledge.evaluation.evidence_metrics import (
    calculate_evidence_gate_metrics,
    calculate_evidence_selection_metrics,
)
from app.risk_knowledge.evaluation.regression import decide_regression
from app.risk_knowledge.evaluation.retrieval_metrics import calculate_retrieval_metrics
from app.risk_knowledge.evaluation.rerank_metrics import calculate_rerank_metrics
from app.risk_knowledge.evaluation.schemas import (
    EvaluationConfig,
    ExpectedEvidence,
    GoldenCaseResult,
    GoldenEvaluationCase,
    GoldenEvaluationReport,
    GoldenEvaluationSummary,
    RegressionThresholds,
)
from app.risk_knowledge.evidence.schemas import (
    Citation,
    EvidenceGateDecision,
    EvidenceGateReason,
    EvidenceGateStatus,
    RiskEvidenceBundle,
    SelectedEvidence,
)
from app.risk_knowledge.retrieval.schemas import (
    HybridRetrievalCandidate,
    HybridRetrievalResult,
    RetrievalQuery,
    RetrievalScopeType,
)
from app.risk_knowledge.reranking.schemas import RerankItem, RerankResult
from app.risk_knowledge.service.schemas import (
    RenderedCitation,
    RiskKnowledgeAnswer,
    RiskKnowledgeAnswerTrace,
    RiskEvidenceBuildTrace,
    RiskKnowledgeQuery,
)


class TraceExecutor(Protocol):
    def __call__(self, case: GoldenEvaluationCase) -> RiskKnowledgeAnswerTrace:
        ...


class RiskKnowledgeGoldenEvaluator:
    def __init__(
        self,
        *,
        executor: TraceExecutor,
        config: EvaluationConfig | None = None,
        thresholds: RegressionThresholds | None = None,
    ) -> None:
        self._executor = executor
        self._config = config or EvaluationConfig(mode="fixture", dataset_path="memory://inline")
        self._thresholds = thresholds or RegressionThresholds()

    def evaluate(self, cases: list[GoldenEvaluationCase]) -> GoldenEvaluationReport:
        case_results: list[GoldenCaseResult] = []
        failures: list[dict[str, object]] = []

        for case in cases:
            try:
                trace = self._executor(case)
            except Exception as exc:  # pragma: no cover - exercised in runtime/manual mode
                failures.append({"case_id": case.case_id, "reason": "execution_failed", "error": str(exc)})
                continue
            case_results.append(_evaluate_case(case, trace))

        summary = _summarize_results(case_results)
        decision = decide_regression(summary, self._thresholds)
        return GoldenEvaluationReport(
            run_id=datetime.now(timezone.utc).strftime("m2d_eval_%Y%m%dT%H%M%SZ"),
            created_at=datetime.now(timezone.utc).isoformat(),
            config=self._config,
            summary=summary,
            case_results=case_results,
            failures=failures,
            regression_decision=decision,
        )


def build_fixture_executor() -> TraceExecutor:
    return _build_fixture_trace


def _evaluate_case(case: GoldenEvaluationCase, trace: RiskKnowledgeAnswerTrace) -> GoldenCaseResult:
    retrieval_metrics = calculate_retrieval_metrics(case, trace.build_trace.retrieval_result)
    rerank_metrics = calculate_rerank_metrics(
        case,
        trace.build_trace.retrieval_result,
        trace.build_trace.rerank_result,
    )
    evidence_metrics = calculate_evidence_selection_metrics(case, trace.build_trace.bundle)
    gate_metrics = calculate_evidence_gate_metrics(case, trace.answer)
    citation_metrics = calculate_citation_metrics(
        case=case,
        rendered_citations=trace.answer.citations,
        bundle_citations=trace.build_trace.bundle.citations,
        selected_evidence=trace.build_trace.bundle.selected_evidence,
        should_answer=trace.answer.should_answer,
    )
    answer_metrics = calculate_answer_metrics(case, trace.answer)
    pr_c_diagnostics = _build_pr_c_diagnostics(case, trace.answer)

    passed = _determine_case_pass(case, trace.answer, gate_metrics, citation_metrics, answer_metrics, pr_c_diagnostics)
    return GoldenCaseResult(
        case_id=case.case_id,
        query=case.query,
        expected_behavior=case.expected_behavior,
        actual_should_answer=trace.answer.should_answer,
        passed=passed,
        retrieval_metrics=retrieval_metrics,
        rerank_metrics=rerank_metrics,
        evidence_metrics=evidence_metrics,
        gate_metrics=gate_metrics,
        citation_metrics=citation_metrics,
        answer_metrics=answer_metrics,
        diagnostics={
            "retrieval_candidate_count": len(trace.build_trace.retrieval_result.candidates),
            "selected_count": len(trace.build_trace.bundle.selected_evidence),
            "answer_type": trace.answer.answer_type,
            **pr_c_diagnostics,
        },
    )


def _determine_case_pass(case, answer, gate_metrics, citation_metrics, answer_metrics, diagnostics) -> bool | None:
    if case.expected_behavior == "ambiguous":
        return None
    extra_checks = _pr_c_extra_checks_pass(diagnostics)
    if case.expected_behavior == "refuse":
        return (
            answer.should_answer is False
            and gate_metrics.gate_correct
            and citation_metrics.invalid_citation_count == 0
            and extra_checks
        )
    return (
        answer.should_answer is True
        and gate_metrics.gate_correct
        and citation_metrics.citation_correct
        and (answer_metrics.expected_points_total == 0 or answer_metrics.matched_points > 0)
        and extra_checks
    )


def _summarize_results(case_results: list[GoldenCaseResult]) -> GoldenEvaluationSummary:
    total_cases = len(case_results)
    answer_cases = sum(1 for case in case_results if case.expected_behavior == "answer")
    refusal_cases = sum(1 for case in case_results if case.expected_behavior == "refuse")
    ambiguous_cases = sum(1 for case in case_results if case.expected_behavior == "ambiguous")

    scored_cases = [case for case in case_results if case.expected_behavior != "ambiguous"]
    refusal_scored = [case for case in case_results if case.expected_behavior == "refuse"]
    answer_scored = [case for case in case_results if case.expected_behavior == "answer"]

    return GoldenEvaluationSummary(
        status="completed",
        total_cases=total_cases,
        answer_cases=answer_cases,
        refusal_cases=refusal_cases,
        ambiguous_cases=ambiguous_cases,
        retrieval_recall_at_5=_avg(case.retrieval_metrics.recall_at_5 for case in scored_cases),
        retrieval_recall_at_10=_avg(case.retrieval_metrics.recall_at_10 for case in scored_cases),
        retrieval_mrr=_avg(case.retrieval_metrics.mrr for case in scored_cases),
        rerank_hit_at_3=_avg(1.0 if case.rerank_metrics.rerank_hit_at_3 else 0.0 for case in scored_cases),
        evidence_precision=_avg(case.evidence_metrics.evidence_precision for case in scored_cases),
        evidence_recall=_avg(case.evidence_metrics.evidence_recall for case in scored_cases),
        gate_accuracy=_avg(1.0 if case.gate_metrics.gate_correct else 0.0 for case in scored_cases),
        refusal_accuracy=_avg(1.0 if case.gate_metrics.gate_correct else 0.0 for case in refusal_scored),
        false_answer_rate=_avg(1.0 if case.actual_should_answer else 0.0 for case in refusal_scored),
        false_refusal_rate=_avg(0.0 if case.actual_should_answer else 1.0 for case in answer_scored),
        citation_correctness=_avg(1.0 if case.citation_metrics.citation_correct else 0.0 for case in answer_scored),
        citation_validity_rate=_avg(1.0 if case.citation_metrics.citation_correct else 0.0 for case in answer_scored),
        answer_point_recall=_avg(case.answer_metrics.answer_point_recall for case in answer_scored),
        context_isolation_pass_rate=_avg(
            1.0
            if int((case.diagnostics or {}).get("forbidden_source_violation_count", 0)) == 0
            else 0.0
            for case in scored_cases
        ),
    )


def _avg(values) -> float:
    items = list(values)
    return 0.0 if not items else sum(items) / len(items)


def _build_pr_c_diagnostics(case: GoldenEvaluationCase, answer: RiskKnowledgeAnswer) -> dict[str, object]:
    route_matches = case.expected_route is None or answer.type == case.expected_route
    grounding_status_matches = (
        case.expected_grounding_status is None or answer.grounding_status == case.expected_grounding_status
    )
    expected_refusal_matches = (
        case.expected_refusal is None or (not answer.should_answer) == bool(case.expected_refusal)
    )

    evidence_texts = [item.evidence_text for item in answer.evidence_trace]
    if not evidence_texts:
        evidence_texts = [item.text for item in answer.evidence_bundle.selected_evidence]
    evidence_blob = "\n".join(text.lower() for text in evidence_texts)
    missing_required_evidence_keywords = [
        keyword
        for keyword in case.required_evidence_keywords
        if str(keyword or "").strip() and str(keyword).lower() not in evidence_blob
    ]

    forbidden_source_violation_count = sum(
        1
        for item in answer.evidence_trace
        if item.source_type in set(case.forbidden_source_types)
    )
    missing_warning_codes = [
        code
        for code in case.must_include_warning_codes
        if code not in {warning.code for warning in answer.warnings}
    ]
    min_citation_count_satisfied = len(answer.citations) >= case.min_citation_count

    return {
        "route_matches": route_matches,
        "grounding_status_matches": grounding_status_matches,
        "expected_refusal_matches": expected_refusal_matches,
        "missing_required_evidence_keywords": missing_required_evidence_keywords,
        "forbidden_source_violation_count": forbidden_source_violation_count,
        "missing_warning_codes": missing_warning_codes,
        "min_citation_count_satisfied": min_citation_count_satisfied,
    }


def _pr_c_extra_checks_pass(diagnostics: dict[str, object]) -> bool:
    return bool(
        diagnostics.get("route_matches", True)
        and diagnostics.get("grounding_status_matches", True)
        and diagnostics.get("expected_refusal_matches", True)
        and diagnostics.get("min_citation_count_satisfied", True)
        and not diagnostics.get("missing_required_evidence_keywords")
        and not diagnostics.get("missing_warning_codes")
        and int(diagnostics.get("forbidden_source_violation_count", 0)) == 0
    )


def _build_fixture_trace(case: GoldenEvaluationCase) -> RiskKnowledgeAnswerTrace:
    should_answer = case.expected_behavior == "answer"
    selected = [_build_selected_from_expected(index, expected) for index, expected in enumerate(case.expected_evidence, start=1)]
    if should_answer and not selected:
        selected = [_build_selected_from_expected(1, ExpectedEvidence(text_contains=[case.query]))]

    candidates = [_build_candidate_from_selected(item) for item in selected]
    retrieval_result = HybridRetrievalResult(
        query=case.query,
        normalized_query=case.query.strip(),
        kb_id=case.kb_id or DEFAULT_RISK_KB_ID,
        scope_type=RetrievalScopeType.KB_ACTIVE_DOCUMENTS,
        active_manifest_index_ids=[item.manifest_index_id for item in selected] or [],
        embedding_provider="deterministic",
        embedding_model="deterministic-v1",
        embedding_dimension=2,
        candidates=candidates,
        diagnostics={"mode": "fixture"},
    )

    rerank_result = None
    if candidates:
        rerank_result = RerankResult(
            provider="deterministic",
            model="deterministic-rerank-v1",
            items=[
                RerankItem(
                    candidate_index=index - 1,
                    candidate_id=item.candidate_id,
                    chunk_id=item.chunk_id,
                    rerank_score=item.rerank_score,
                    rerank_rank=index,
                )
                for index, item in enumerate(selected, start=1)
            ],
        )

    citations = [
        Citation(
            citation_id=f"cite_{item.chunk_id}",
            evidence_id=item.evidence_id,
            document_id=item.document_id,
            version_id=item.version_id,
            chunk_id=item.chunk_id,
            content_hash=item.content_hash,
            section_path=item.section_path,
            page_start=item.page_start,
            page_end=item.page_end,
            manifest_index_id=item.manifest_index_id,
            evidence_rank=item.selected_rank,
        )
        for item in selected
    ]
    gate_reason = EvidenceGateReason.SUFFICIENT if should_answer else EvidenceGateReason(case.expected_refusal_reason or "no_candidates")
    bundle = RiskEvidenceBundle(
        query=case.query,
        normalized_query=case.query.strip(),
        kb_id=case.kb_id,
        scope_type=RetrievalScopeType.KB_ACTIVE_DOCUMENTS,
        active_manifest_index_ids=[item.manifest_index_id for item in selected] or [],
        retrieval_diagnostics={"mode": "fixture"},
        rerank_provider="deterministic",
        rerank_model="deterministic-rerank-v1",
        selected_evidence=selected if should_answer else [],
        citations=citations if should_answer else [],
        gate_decision=EvidenceGateDecision(
            should_answer=should_answer,
            status=EvidenceGateStatus.SUFFICIENT if should_answer else EvidenceGateStatus.INSUFFICIENT,
            reason=gate_reason,
            confidence=0.9 if should_answer else 0.1,
            diagnostics={"selected_count": len(selected)},
        ),
        should_answer=should_answer,
        refusal_reason=None if should_answer else gate_reason.value,
    )
    rendered = [
        RenderedCitation(
            citation_id=citation.citation_id,
            label=f"[{index}] {citation.document_id} / {citation.chunk_id}",
            document_id=citation.document_id,
            document_title=citation.document_id,
            version_id=citation.version_id,
            chunk_id=citation.chunk_id,
            section_path=" / ".join(citation.section_path),
            page_start=citation.page_start,
            page_end=citation.page_end,
        )
        for index, citation in enumerate(bundle.citations, start=1)
    ]
    answer_text = (
        " ".join(case.expected_answer_points) + (f"[{rendered[0].citation_id}]" if rendered else "")
        if should_answer
        else "当前知识库中没有足够证据支持回答该问题。"
    )
    answer = RiskKnowledgeAnswer(
        query=case.query,
        normalized_query=case.query.strip(),
        answer=answer_text,
        answer_type="grounded_answer" if should_answer else "refusal",
        should_answer=should_answer,
        refusal_reason=None if should_answer else bundle.refusal_reason,
        evidence_bundle=bundle,
        citations=rendered if should_answer else [],
        used_citation_ids=[item.citation_id for item in rendered] if should_answer else [],
        diagnostics={"mode": "fixture"},
    )
    return RiskKnowledgeAnswerTrace(
        query=RiskKnowledgeQuery(
            query=case.query,
            kb_id=case.kb_id,
            document_id=case.document_id,
            version_id=case.version_id,
            intent=case.intent,
        ),
        build_trace=RiskEvidenceBuildTrace(
            retrieval_query=RetrievalQuery(query=case.query, kb_id=case.kb_id, document_id=case.document_id, version_id=case.version_id),
            retrieval_result=retrieval_result,
            rerank_result=rerank_result,
            bundle=bundle,
        ),
        answer=answer,
    )


def _build_selected_from_expected(index: int, expected: ExpectedEvidence) -> SelectedEvidence:
    chunk_id = expected.chunk_id or f"risk_chunk_{index:03d}"
    document_id = expected.document_id or "risk_guide"
    version_id = expected.version_id or f"{document_id}_v1"
    content_hash = expected.content_hash or f"sha256:{chunk_id}"
    tokens = expected.text_contains or [expected.section_path_contains or "风险信号"]
    text = " ".join(tokens)
    section_tail = expected.section_path_contains or chunk_id
    return SelectedEvidence(
        evidence_id=f"evid_{chunk_id}",
        candidate_id=f"cand_{chunk_id}",
        chunk_id=chunk_id,
        document_id=document_id,
        version_id=version_id,
        manifest_index_id=f"idx_{document_id}",
        content_hash=content_hash,
        text=text,
        section_path=[document_id, section_tail],
        page_start=1,
        page_end=1,
        retrieval_fused_score=max(0.5, 1.0 - (index * 0.05)),
        retrieval_fused_rank=index,
        rerank_score=max(0.5, 1.0 - (index * 0.05)),
        rerank_rank=index,
        selected_rank=index,
        matched_channels=["vector", "keyword"],
    )


def _build_candidate_from_selected(item: SelectedEvidence) -> HybridRetrievalCandidate:
    return HybridRetrievalCandidate(
        retrieval_key=f"{item.manifest_index_id}:{item.chunk_id}",
        chunk_id=item.chunk_id,
        document_id=item.document_id,
        version_id=item.version_id,
        manifest_index_id=item.manifest_index_id,
        content_hash=item.content_hash,
        section_path=item.section_path,
        page_start=item.page_start,
        page_end=item.page_end,
        text=item.text,
        vector_raw_score=0.1,
        keyword_score=0.9,
        vector_rank=item.retrieval_fused_rank,
        keyword_rank=item.retrieval_fused_rank,
        fused_score=item.retrieval_fused_score,
        fused_rank=item.retrieval_fused_rank,
        matched_channels=item.matched_channels,
    )
