"""Risk QA groundedness evaluator backed by deterministic runtime seams."""

from __future__ import annotations

import hashlib
from typing import Any

from app.eval.evaluators.base import BaseEvaluator
from app.eval.schemas import EvalCase, EvalResult
from app.knowledge_base.config import DEFAULT_RISK_KB_ID
from app.risk_knowledge.context import ContextBuildRequest, RiskQaContextBuilder
from app.risk_knowledge.evidence.schemas import (
    Citation,
    EvidenceGateDecision,
    EvidenceGateReason,
    EvidenceGateStatus,
    RiskEvidenceBundle,
    SelectedEvidence,
)
from app.risk_knowledge.qa.citation_validation import CitationValidator
from app.risk_knowledge.qa.sufficiency import EvidenceSufficiencyChecker
from app.risk_knowledge.retrieval.schemas import (
    HybridRetrievalCandidate,
    HybridRetrievalResult,
    RetrievalScopeType,
)
from app.risk_knowledge.service.schemas import EvidenceTraceItem, RenderedCitation, RiskQaWarning


class RiskQAEvaluator(BaseEvaluator):
    def __init__(self) -> None:
        self._context_builder = RiskQaContextBuilder()
        self._citation_validator = CitationValidator()
        self._sufficiency_checker = EvidenceSufficiencyChecker()

    def evaluate_case(self, case: EvalCase) -> EvalResult:
        check_kind = str(case.input.get("check_kind") or "").strip()
        if check_kind == "retrieval_grounding":
            return self._evaluate_retrieval_grounding(case)
        if check_kind == "evidence_sufficiency":
            return self._evaluate_evidence_sufficiency(case)
        if check_kind == "citation_validation":
            return self._evaluate_citation_validation(case)
        if check_kind == "answer_grounding":
            return self._evaluate_answer_grounding(case)
        if check_kind == "refusal_policy":
            return self._evaluate_refusal_policy(case)
        if check_kind == "unsupported_claim":
            return self._evaluate_unsupported_claim(case)
        if check_kind == "source_boundary":
            return self._evaluate_source_boundary(case)
        raise ValueError(f"unsupported risk qa check_kind: {check_kind}")

    def build_suite_metrics(self, results: list[EvalResult]) -> dict[str, Any]:
        retrieval_results = [result for result in results if result.metrics.get("check_kind") == "retrieval_grounding"]
        citation_results = [result for result in results if result.metrics.get("check_kind") == "citation_validation"]
        grounding_results = [result for result in results if result.metrics.get("check_kind") == "answer_grounding"]
        sufficiency_results = [
            result
            for result in results
            if result.metrics.get("check_kind") in {"evidence_sufficiency", "refusal_policy"}
        ]
        refusal_results = [result for result in results if result.metrics.get("check_kind") == "refusal_policy"]
        unsupported_results = [result for result in results if result.metrics.get("check_kind") == "unsupported_claim"]
        boundary_results = [result for result in results if result.metrics.get("check_kind") == "source_boundary"]
        return {
            "risk_qa_groundedness_pass_rate": _pass_rate(results),
            "retrieval_expected_section_hit_rate": _pass_rate(retrieval_results),
            "citation_presence_rate": _ratio(
                citation_results + grounding_results,
                lambda result: bool(result.artifacts.get("citation_ids")),
            ),
            "citation_validity_rate": _ratio(
                citation_results + grounding_results + refusal_results,
                lambda result: "RISK_QA_CITATION_INVALID" not in list(result.artifacts.get("normalized_failures") or []),
            ),
            "evidence_sufficiency_pass_rate": _pass_rate(sufficiency_results),
            "insufficient_evidence_refusal_rate": _ratio(
                refusal_results,
                lambda result: bool(result.artifacts.get("refusal_reason")),
            ),
            "unsupported_claim_block_rate": _pass_rate(unsupported_results),
            "source_boundary_block_rate": _pass_rate(boundary_results),
        }

    def _evaluate_retrieval_grounding(self, case: EvalCase) -> EvalResult:
        runtime = _build_runtime_case(case.input)
        actual_decision = "allowed"
        raw_failures: list[str] = []
        raw_warnings: list[str] = []

        required_sections = [str(item) for item in case.expected.get("required_section_ids", [])]
        actual_sections = list(runtime["record_section_ids"])
        missing_sections = [section_id for section_id in required_sections if section_id not in actual_sections]
        if missing_sections:
            actual_decision = "blocked"
            raw_failures.append("RISK_QA_EXPECTED_SECTION_MISSING")

        required_chunks = [str(item) for item in case.expected.get("required_chunk_ids", [])]
        actual_chunks = list(runtime["retrieved_chunk_ids"])
        missing_chunks = [chunk_id for chunk_id in required_chunks if chunk_id not in actual_chunks]
        if missing_chunks:
            actual_decision = "blocked"
            raw_failures.append("RISK_QA_RETRIEVAL_MISS")

        if not actual_chunks and not raw_failures:
            actual_decision = "blocked"
            raw_failures.append("RISK_QA_RETRIEVAL_MISS")

        normalized_failures = _normalize_codes(raw_failures)
        normalized_warnings = _normalize_codes(raw_warnings)
        failures = _compare_common_expectations(
            expected=case.expected,
            actual_decision=actual_decision,
            actual_warning_codes=normalized_warnings,
            actual_failure_codes=normalized_failures,
        )
        if actual_decision != "blocked":
            failures.extend(
                _compare_required_values(
                    label="chunk_ids",
                    expected=case.expected.get("required_chunk_ids", []),
                    actual=actual_chunks,
                )
            )
            failures.extend(
                _compare_required_values(
                    label="section_ids",
                    expected=case.expected.get("required_section_ids", []),
                    actual=actual_sections,
                )
            )
        failures.extend(
            _compare_forbidden_values(
                label="chunk_ids",
                expected=case.expected.get("forbidden_chunk_ids", []),
                actual=actual_chunks,
            )
        )
        if "min_evidence_count" in case.expected:
            minimum = int(case.expected.get("min_evidence_count") or 0)
            if len(actual_chunks) < minimum:
                failures.append(f"expected at least {minimum} evidence chunks but got {len(actual_chunks)}")

        return _build_result(
            case=case,
            check_kind="retrieval_grounding",
            actual_decision=actual_decision,
            raw_warnings=raw_warnings,
            normalized_warnings=normalized_warnings,
            raw_failures=raw_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "adapter",
                "check_kind": "retrieval_grounding",
                "raw_decision": actual_decision,
                "retrieved_chunk_ids": actual_chunks,
                "selected_evidence_ids": list(runtime["selected_evidence_ids"]),
                "citation_ids": [],
                "refusal_reason": None,
                "raw_source_labels": list(runtime["raw_source_labels"]),
                "mapped_source_types": list(runtime["mapped_source_types"]),
                "blocked_context_sources": [],
                "record_section_ids": actual_sections,
            },
        )

    def _evaluate_evidence_sufficiency(self, case: EvalCase) -> EvalResult:
        runtime = _build_runtime_case(case.input)
        sufficiency = self._sufficiency_checker.check(
            bundle=runtime["bundle"],
            evidence_trace=runtime["evidence_trace"],
        )
        raw_warnings = [warning.code for warning in sufficiency.warnings if warning.severity != "blocker"]
        raw_failures = [warning.code for warning in sufficiency.warnings if warning.severity == "blocker"]
        actual_decision = _sufficiency_status_to_decision(sufficiency.status)
        normalized_failures = _normalize_codes(raw_failures)
        normalized_warnings = _normalize_codes(raw_warnings)

        failures = _compare_common_expectations(
            expected=case.expected,
            actual_decision=actual_decision,
            actual_warning_codes=normalized_warnings,
            actual_failure_codes=normalized_failures,
        )
        expected_refusal = case.expected.get("expected_refusal")
        if expected_refusal is not None:
            actual_refusal = sufficiency.status == "insufficient_evidence"
            if actual_refusal != bool(expected_refusal):
                failures.append(f"expected_refusal {expected_refusal} but got {actual_refusal}")

        if "min_evidence_count" in case.expected:
            minimum = int(case.expected.get("min_evidence_count") or 0)
            if len(runtime["evidence_trace"]) < minimum:
                failures.append(
                    f"expected at least {minimum} evidence items but got {len(runtime['evidence_trace'])}"
                )

        return _build_result(
            case=case,
            check_kind="evidence_sufficiency",
            actual_decision=actual_decision,
            raw_warnings=raw_warnings,
            normalized_warnings=normalized_warnings,
            raw_failures=raw_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "runtime",
                "check_kind": "evidence_sufficiency",
                "raw_decision": sufficiency.status,
                "retrieved_chunk_ids": list(runtime["retrieved_chunk_ids"]),
                "selected_evidence_ids": list(runtime["selected_evidence_ids"]),
                "citation_ids": [],
                "refusal_reason": sufficiency.reason if sufficiency.status == "insufficient_evidence" else None,
                "raw_source_labels": list(runtime["raw_source_labels"]),
                "mapped_source_types": list(runtime["mapped_source_types"]),
                "blocked_context_sources": [],
                "grounding_status": sufficiency.status,
            },
        )

    def _evaluate_citation_validation(self, case: EvalCase) -> EvalResult:
        runtime = _build_runtime_case(case.input)
        validation = self._run_citation_validation(runtime, case.input)
        raw_failures = [warning.code for warning in validation.blockers]
        raw_warnings = [warning.code for warning in validation.warnings]
        actual_decision = _citation_validation_to_decision(validation)
        normalized_failures = _normalize_codes(raw_failures)
        normalized_warnings = _normalize_codes(raw_warnings)

        failures = _compare_common_expectations(
            expected=case.expected,
            actual_decision=actual_decision,
            actual_warning_codes=normalized_warnings,
            actual_failure_codes=normalized_failures,
        )
        failures.extend(
            _compare_required_values(
                label="citations",
                expected=case.expected.get("required_citations", []),
                actual=runtime["citation_chunk_ids"],
            )
        )

        return _build_result(
            case=case,
            check_kind="citation_validation",
            actual_decision=actual_decision,
            raw_warnings=raw_warnings,
            normalized_warnings=normalized_warnings,
            raw_failures=raw_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "runtime",
                "check_kind": "citation_validation",
                "raw_decision": actual_decision,
                "retrieved_chunk_ids": list(runtime["retrieved_chunk_ids"]),
                "selected_evidence_ids": list(runtime["selected_evidence_ids"]),
                "citation_ids": list(runtime["citation_ids"]),
                "refusal_reason": None,
                "raw_source_labels": list(runtime["raw_source_labels"]),
                "mapped_source_types": list(runtime["mapped_source_types"]),
                "blocked_context_sources": [],
            },
        )

    def _evaluate_answer_grounding(self, case: EvalCase) -> EvalResult:
        runtime = _build_runtime_case(case.input)
        validation = self._run_citation_validation(runtime, case.input)
        raw_failures = [warning.code for warning in validation.blockers]
        raw_warnings = [warning.code for warning in validation.warnings]
        answer_text = str((case.input.get("answer") or {}).get("text") or "")

        actual_decision = "blocked" if validation.blockers else "allowed"

        token_failures = _compare_tokens(
            rendered_text=answer_text,
            required_tokens=case.expected.get("required_answer_tokens", []),
            forbidden_tokens=case.expected.get("forbidden_answer_tokens", []),
        )
        if token_failures:
            actual_decision = "blocked"
            raw_failures.append("RISK_QA_UNSUPPORTED_CLAIM")

        normalized_failures = _normalize_codes(raw_failures)
        normalized_warnings = _normalize_codes(raw_warnings)
        failures = _compare_common_expectations(
            expected=case.expected,
            actual_decision=actual_decision,
            actual_warning_codes=normalized_warnings,
            actual_failure_codes=normalized_failures,
        )
        failures.extend(token_failures)
        failures.extend(
            _compare_required_values(
                label="citations",
                expected=case.expected.get("required_citations", []),
                actual=runtime["citation_chunk_ids"],
            )
        )

        return _build_result(
            case=case,
            check_kind="answer_grounding",
            actual_decision=actual_decision,
            raw_warnings=raw_warnings,
            normalized_warnings=normalized_warnings,
            raw_failures=raw_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "adapter",
                "check_kind": "answer_grounding",
                "raw_decision": actual_decision,
                "retrieved_chunk_ids": list(runtime["retrieved_chunk_ids"]),
                "selected_evidence_ids": list(runtime["selected_evidence_ids"]),
                "citation_ids": list(runtime["citation_ids"]),
                "refusal_reason": None,
                "raw_source_labels": list(runtime["raw_source_labels"]),
                "mapped_source_types": list(runtime["mapped_source_types"]),
                "blocked_context_sources": [],
            },
        )

    def _evaluate_refusal_policy(self, case: EvalCase) -> EvalResult:
        runtime = _build_runtime_case(case.input)
        sufficiency = self._sufficiency_checker.check(
            bundle=runtime["bundle"],
            evidence_trace=runtime["evidence_trace"],
        )
        raw_failures = [warning.code for warning in sufficiency.warnings if warning.severity == "blocker"]
        raw_warnings = [warning.code for warning in sufficiency.warnings if warning.severity != "blocker"]
        actual_decision = "refused" if sufficiency.status == "insufficient_evidence" else _sufficiency_status_to_decision(
            sufficiency.status
        )

        answer_payload = dict(case.input.get("answer") or {})
        if "citations" in answer_payload:
            validation = self._run_citation_validation(runtime, case.input)
            raw_failures.extend(warning.code for warning in validation.blockers)
            raw_warnings.extend(warning.code for warning in validation.warnings)
            if validation.blockers:
                actual_decision = "blocked"

        normalized_failures = _normalize_codes(raw_failures)
        normalized_warnings = _normalize_codes(raw_warnings)
        failures = _compare_common_expectations(
            expected=case.expected,
            actual_decision=actual_decision,
            actual_warning_codes=normalized_warnings,
            actual_failure_codes=normalized_failures,
        )
        expected_refusal = case.expected.get("expected_refusal")
        if expected_refusal is not None:
            actual_refusal = sufficiency.status == "insufficient_evidence"
            if actual_refusal != bool(expected_refusal):
                failures.append(f"expected_refusal {expected_refusal} but got {actual_refusal}")

        return _build_result(
            case=case,
            check_kind="refusal_policy",
            actual_decision=actual_decision,
            raw_warnings=raw_warnings,
            normalized_warnings=normalized_warnings,
            raw_failures=raw_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "runtime",
                "check_kind": "refusal_policy",
                "raw_decision": actual_decision,
                "retrieved_chunk_ids": list(runtime["retrieved_chunk_ids"]),
                "selected_evidence_ids": list(runtime["selected_evidence_ids"]),
                "citation_ids": list(runtime["citation_ids"]),
                "refusal_reason": sufficiency.reason if sufficiency.status == "insufficient_evidence" else None,
                "raw_source_labels": list(runtime["raw_source_labels"]),
                "mapped_source_types": list(runtime["mapped_source_types"]),
                "blocked_context_sources": [],
                "grounding_status": sufficiency.status,
            },
        )

    def _evaluate_unsupported_claim(self, case: EvalCase) -> EvalResult:
        runtime = _build_runtime_case(case.input)
        validation = self._run_citation_validation(runtime, case.input)
        raw_failures = [warning.code for warning in validation.blockers]
        raw_warnings = [warning.code for warning in validation.warnings]
        answer_text = str((case.input.get("answer") or {}).get("text") or "")
        forbidden_tokens = [str(token) for token in case.expected.get("forbidden_answer_tokens", [])]
        actual_unsupported_claims = [token for token in forbidden_tokens if token and token in answer_text]
        if actual_unsupported_claims:
            raw_failures.append("RISK_QA_UNSUPPORTED_CLAIM")

        actual_decision = "blocked" if raw_failures else "allowed"
        normalized_failures = _normalize_codes(raw_failures)
        normalized_warnings = _normalize_codes(raw_warnings)

        failures = _compare_common_expectations(
            expected=case.expected,
            actual_decision=actual_decision,
            actual_warning_codes=normalized_warnings,
            actual_failure_codes=normalized_failures,
        )
        return _build_result(
            case=case,
            check_kind="unsupported_claim",
            actual_decision=actual_decision,
            raw_warnings=raw_warnings,
            normalized_warnings=normalized_warnings,
            raw_failures=raw_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "adapter",
                "check_kind": "unsupported_claim",
                "raw_decision": actual_decision,
                "retrieved_chunk_ids": list(runtime["retrieved_chunk_ids"]),
                "selected_evidence_ids": list(runtime["selected_evidence_ids"]),
                "citation_ids": list(runtime["citation_ids"]),
                "refusal_reason": None,
                "raw_source_labels": list(runtime["raw_source_labels"]),
                "mapped_source_types": list(runtime["mapped_source_types"]),
                "blocked_context_sources": [],
                "unsupported_claims": actual_unsupported_claims,
            },
        )

    def _evaluate_source_boundary(self, case: EvalCase) -> EvalResult:
        runtime = _build_runtime_case(case.input)
        context = self._context_builder.build(
            ContextBuildRequest(
                task_type="risk_knowledge_answer",
                query=str(case.input.get("query") or case.input.get("question") or ""),
                selected_evidence_ids=list(runtime["selected_evidence_ids"]),
            )
        )
        raw_warnings = [warning.code for warning in context.isolation_warnings]
        raw_failures: list[str] = []
        blocked_labels: list[str] = []
        for raw_label, mapped_type in zip(runtime["raw_source_labels"], runtime["mapped_source_types"], strict=False):
            if mapped_type in context.allowed_context_sources:
                continue
            blocked_labels.append(raw_label)
            if raw_label == "risk_qa_answer":
                raw_failures.append("RISK_QA_HISTORY_NOT_SOURCE_DOCUMENT")
            elif mapped_type == "sql_examples":
                raw_failures.append("RISK_QA_DATA_KNOWLEDGE_LEAKAGE")
            else:
                raw_failures.append("RISK_QA_SOURCE_BOUNDARY_VIOLATION")

        actual_decision = "blocked" if blocked_labels else "allowed"
        normalized_failures = _normalize_codes(raw_failures)
        normalized_warnings = _normalize_codes(raw_warnings)
        failures = _compare_common_expectations(
            expected=case.expected,
            actual_decision=actual_decision,
            actual_warning_codes=normalized_warnings,
            actual_failure_codes=normalized_failures,
        )

        return _build_result(
            case=case,
            check_kind="source_boundary",
            actual_decision=actual_decision,
            raw_warnings=raw_warnings,
            normalized_warnings=normalized_warnings,
            raw_failures=raw_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "runtime",
                "check_kind": "source_boundary",
                "raw_decision": actual_decision,
                "retrieved_chunk_ids": list(runtime["retrieved_chunk_ids"]),
                "selected_evidence_ids": list(runtime["selected_evidence_ids"]),
                "citation_ids": [],
                "refusal_reason": None,
                "raw_source_labels": list(runtime["raw_source_labels"]),
                "mapped_source_types": list(runtime["mapped_source_types"]),
                "blocked_context_sources": list(context.blocked_context_sources),
                "context_hash": context.context_hash,
            },
        )

    def _run_citation_validation(self, runtime: dict[str, Any], input_payload: dict[str, Any]):
        answer = dict(input_payload.get("answer") or {})
        return self._citation_validator.validate(
            citations=list(runtime["rendered_citations"]),
            evidence_trace=list(runtime["evidence_trace"]),
            used_citation_ids=[citation.citation_id for citation in runtime["rendered_citations"]] if "citations" in answer else [],
        )


def _build_runtime_case(payload: dict[str, Any]) -> dict[str, Any]:
    records = list(payload.get("records") or [])
    query = str(payload.get("query") or payload.get("question") or "")
    selected_evidence = [_record_to_selected_evidence(index, record) for index, record in enumerate(records, start=1)]
    citations = [_selected_evidence_to_citation(evidence) for evidence in selected_evidence]
    rendered_citations = _build_rendered_citations(
        records=records,
        selected_evidence=selected_evidence,
        answer_payload=dict(payload.get("answer") or {}),
    )
    retrieval_result = _build_retrieval_result(query=query, selected_evidence=selected_evidence)
    evidence_trace = [
        _selected_evidence_to_trace_item(evidence)
        for evidence in selected_evidence
    ]
    bundle = RiskEvidenceBundle(
        query=query or "synthetic risk qa query",
        normalized_query=(query or "synthetic risk qa query").strip(),
        kb_id=str((payload.get("metadata") or {}).get("kb_id") or DEFAULT_RISK_KB_ID),
        scope_type=RetrievalScopeType.KB_ACTIVE_DOCUMENTS,
        active_manifest_index_ids=[evidence.manifest_index_id for evidence in selected_evidence],
        retrieval_diagnostics={"record_count": len(records)},
        rerank_provider="deterministic",
        rerank_model="deterministic-risk-qa-eval-v1",
        selected_evidence=selected_evidence,
        citations=citations,
        gate_decision=_build_gate_decision(selected_evidence),
        should_answer=bool(selected_evidence),
        refusal_reason=None if selected_evidence else EvidenceGateReason.NO_CANDIDATES.value,
    )
    raw_source_labels = [str(record.get("raw_source_label") or record.get("source_type") or "risk_domain_knowledge") for record in records]
    mapped_source_types = [_map_source_type(label) for label in raw_source_labels]
    citation_ids = [citation.citation_id for citation in rendered_citations]
    citation_chunk_ids = [citation.chunk_id for citation in rendered_citations if citation.chunk_id]
    return {
        "bundle": bundle,
        "retrieval_result": retrieval_result,
        "evidence_trace": evidence_trace,
        "rendered_citations": rendered_citations,
        "retrieved_chunk_ids": [evidence.chunk_id for evidence in selected_evidence],
        "selected_evidence_ids": [item.evidence_id for item in evidence_trace],
        "citation_ids": citation_ids,
        "citation_chunk_ids": citation_chunk_ids,
        "record_section_ids": [str(record.get("section_id") or "").strip() for record in records if str(record.get("section_id") or "").strip()],
        "raw_source_labels": raw_source_labels,
        "mapped_source_types": mapped_source_types,
    }


def _record_to_selected_evidence(position: int, record: dict[str, Any]) -> SelectedEvidence:
    document_id = str(record.get("document_id") or record.get("document_name") or "risk_doc")
    version_id = str(record.get("document_version") or "v1")
    chunk_id = str(record.get("chunk_id") or f"chunk_{position}")
    manifest_index_id = f"idx_{document_id}_{version_id}"
    section_path = _normalize_section_path(record.get("section_path"), fallback_title=record.get("section_title"))
    evidence_text = str(record.get("evidence_text") or record.get("text") or "")
    content_hash = hashlib.sha256(f"{document_id}:{version_id}:{chunk_id}:{evidence_text}".encode("utf-8")).hexdigest()[:16]
    score = float(record.get("relevance_score") or 0.0)
    rerank_score = float(record.get("rerank_score") or score or 0.0)
    return SelectedEvidence(
        evidence_id=f"ev_{chunk_id}",
        candidate_id=f"cand_{chunk_id}",
        chunk_id=chunk_id,
        document_id=document_id,
        version_id=version_id,
        manifest_index_id=manifest_index_id,
        content_hash=content_hash,
        text=evidence_text,
        section_path=section_path,
        page_start=record.get("page_start"),
        page_end=record.get("page_end"),
        retrieval_fused_score=score,
        retrieval_fused_rank=position,
        rerank_score=rerank_score,
        rerank_rank=position,
        selected_rank=position,
        matched_channels=["deterministic_eval"],
    )


def _selected_evidence_to_citation(evidence: SelectedEvidence) -> Citation:
    return Citation(
        citation_id=f"cite_{evidence.chunk_id}",
        evidence_id=evidence.evidence_id,
        document_id=evidence.document_id,
        version_id=evidence.version_id,
        chunk_id=evidence.chunk_id,
        content_hash=evidence.content_hash,
        section_path=list(evidence.section_path),
        page_start=evidence.page_start,
        page_end=evidence.page_end,
        manifest_index_id=evidence.manifest_index_id,
        evidence_rank=evidence.selected_rank,
    )


def _selected_evidence_to_trace_item(evidence: SelectedEvidence) -> EvidenceTraceItem:
    return EvidenceTraceItem(
        evidence_id=evidence.evidence_id,
        source_type="risk_domain_knowledge",
        document_id=evidence.document_id,
        document_name=evidence.section_path[0] if evidence.section_path else evidence.document_id,
        document_version=evidence.version_id,
        section_title=evidence.section_path[-1] if evidence.section_path else None,
        section_path=list(evidence.section_path),
        page_start=evidence.page_start,
        page_end=evidence.page_end,
        chunk_id=evidence.chunk_id,
        evidence_text=evidence.text,
        score=evidence.retrieval_fused_score,
        rerank_score=evidence.rerank_score,
        confidence=evidence.rerank_score,
        used_in_answer=True,
        citation_label=f"[{evidence.selected_rank}] {evidence.document_id}",
        warnings=[],
    )


def _build_retrieval_result(*, query: str, selected_evidence: list[SelectedEvidence]) -> HybridRetrievalResult:
    candidates = [
        HybridRetrievalCandidate(
            retrieval_key=f"{evidence.manifest_index_id}:{evidence.chunk_id}",
            chunk_id=evidence.chunk_id,
            document_id=evidence.document_id,
            version_id=evidence.version_id,
            manifest_index_id=evidence.manifest_index_id,
            content_hash=evidence.content_hash,
            section_path=list(evidence.section_path),
            page_start=evidence.page_start,
            page_end=evidence.page_end,
            text=evidence.text,
            vector_raw_score=evidence.retrieval_fused_score,
            keyword_score=evidence.retrieval_fused_score,
            vector_rank=evidence.retrieval_fused_rank,
            keyword_rank=evidence.retrieval_fused_rank,
            fused_score=evidence.retrieval_fused_score,
            fused_rank=evidence.retrieval_fused_rank,
            matched_channels=list(evidence.matched_channels),
        )
        for evidence in selected_evidence
    ]
    return HybridRetrievalResult(
        query=query or "synthetic risk qa query",
        normalized_query=(query or "synthetic risk qa query").strip(),
        kb_id=DEFAULT_RISK_KB_ID,
        scope_type=RetrievalScopeType.KB_ACTIVE_DOCUMENTS,
        active_manifest_index_ids=[evidence.manifest_index_id for evidence in selected_evidence],
        embedding_provider="deterministic",
        embedding_model="deterministic-risk-qa-eval-v1",
        embedding_dimension=1,
        candidates=candidates,
        diagnostics={"candidate_count": len(candidates)},
    )


def _build_gate_decision(selected_evidence: list[SelectedEvidence]) -> EvidenceGateDecision:
    if not selected_evidence:
        return EvidenceGateDecision(
            should_answer=False,
            status=EvidenceGateStatus.INSUFFICIENT,
            reason=EvidenceGateReason.NO_CANDIDATES,
            confidence=0.0,
            diagnostics={"selected_count": 0},
        )
    return EvidenceGateDecision(
        should_answer=True,
        status=EvidenceGateStatus.SUFFICIENT,
        reason=EvidenceGateReason.SUFFICIENT,
        confidence=float(selected_evidence[0].rerank_score),
        diagnostics={"selected_count": len(selected_evidence)},
    )


def _build_rendered_citations(
    *,
    records: list[dict[str, Any]],
    selected_evidence: list[SelectedEvidence],
    answer_payload: dict[str, Any],
) -> list[RenderedCitation]:
    answer_citations = list(answer_payload.get("citations") or [])
    evidence_by_chunk_id = {evidence.chunk_id: evidence for evidence in selected_evidence}
    records_by_chunk_id = {str(record.get("chunk_id") or ""): record for record in records}
    if not answer_citations:
        return []

    rendered: list[RenderedCitation] = []
    for position, payload in enumerate(answer_citations, start=1):
        chunk_id = str(payload.get("chunk_id") or "")
        evidence = evidence_by_chunk_id.get(chunk_id)
        record = records_by_chunk_id.get(chunk_id, {})
        section_title = str(payload.get("section_title") or record.get("section_title") or "").strip() or None
        section_id = str(payload.get("section_id") or record.get("section_id") or "").strip() or None
        section_path = _normalize_section_path(record.get("section_path"), fallback_title=section_title)
        document_title = str(record.get("document_name") or payload.get("document_name") or record.get("document_id") or "risk_doc")

        page_start = payload.get("page_start")
        if page_start is None and "page_start" not in payload:
            page_start = None
        page_end = payload.get("page_end")
        if page_end is None and page_start is not None and evidence is not None:
            page_end = evidence.page_end

        rendered.append(
            RenderedCitation(
                citation_id=str(payload.get("citation_id") or f"cite_manual_{position}"),
                label=_build_citation_label(document_title=document_title, section_title=section_title, page_start=page_start, page_end=page_end),
                document_id=str(record.get("document_id") or payload.get("document_id") or document_title),
                document_title=document_title,
                version_id=str(record.get("document_version") or payload.get("document_version") or "v1"),
                chunk_id=chunk_id or str(payload.get("chunk_id") or ""),
                evidence_id=evidence.evidence_id if evidence is not None else str(payload.get("evidence_id") or f"ev_{chunk_id or position}"),
                section_path=" / ".join(section_path) if section_path else (section_id or section_title),
                page_start=page_start,
                page_end=page_end,
                quote=evidence.text[:160] if evidence is not None else None,
            )
        )
    return rendered


def _build_citation_label(*, document_title: str, section_title: str | None, page_start: int | None, page_end: int | None) -> str:
    label = document_title
    if section_title:
        label = f"{label} / {section_title}"
    if page_start is not None:
        if page_end is None or page_end == page_start:
            label = f"{label} / p.{page_start}"
        else:
            label = f"{label} / p.{page_start}-{page_end}"
    return label


def _normalize_section_path(value: Any, *, fallback_title: Any = None) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in value.split("/") if part.strip()]
    if fallback_title is not None and str(fallback_title).strip():
        return [str(fallback_title).strip()]
    return []


def _map_source_type(raw_label: str) -> str:
    mapping = {
        "risk_qa_answer": "memory_as_authority",
        "data_sql_example": "sql_examples",
        "data_sql_error_case": "sql_error_cases",
        "catalog_grounding": "catalog_grounding",
        "risk_domain_knowledge": "risk_domain_knowledge",
        "memory_as_authority": "memory_as_authority",
        "sql_examples": "sql_examples",
        "sql_error_cases": "sql_error_cases",
        "data_knowledge": "data_knowledge",
    }
    return mapping.get(raw_label, raw_label)


def _sufficiency_status_to_decision(status: str) -> str:
    if status == "grounded":
        return "allowed"
    if status == "partial":
        return "warning"
    return "refused"


def _citation_validation_to_decision(validation: Any) -> str:
    if validation.blockers:
        return "blocked"
    if validation.warnings:
        return "warning"
    return "allowed"


def _build_result(
    *,
    case: EvalCase,
    check_kind: str,
    actual_decision: str,
    raw_warnings: list[str],
    normalized_warnings: list[str],
    raw_failures: list[str],
    normalized_failures: list[str],
    failures: list[str],
    artifacts: dict[str, Any],
) -> EvalResult:
    return EvalResult(
        case_id=case.case_id,
        suite=case.suite,
        status="PASS" if not failures else "FAIL",
        passed=not failures,
        score=1.0 if not failures else 0.0,
        metrics={
            "check_kind": check_kind,
            "expected_decision": case.expected.get("decision"),
            "actual_decision": actual_decision,
            "expected_warning_codes": list(case.expected.get("required_warning_codes") or []),
            "actual_warning_codes": normalized_warnings,
            "expected_failure_codes": list(case.expected.get("required_failure_codes") or []),
            "actual_failure_codes": normalized_failures,
            "decision_match": not failures,
        },
        failures=failures,
        warnings=list(normalized_warnings),
        artifacts={
            **artifacts,
            "raw_warnings": raw_warnings,
            "normalized_warnings": normalized_warnings,
            "raw_failures": raw_failures,
            "normalized_failures": normalized_failures,
        },
    )


def _compare_common_expectations(
    *,
    expected: dict[str, Any],
    actual_decision: str,
    actual_warning_codes: list[str],
    actual_failure_codes: list[str],
) -> list[str]:
    failures: list[str] = []
    expected_decision = str(expected.get("decision") or "").strip()
    if expected_decision and expected_decision != actual_decision:
        failures.append(f"expected decision {expected_decision} but got {actual_decision}")

    required_warning_codes = [str(item) for item in expected.get("required_warning_codes", [])]
    missing_warning_codes = [item for item in required_warning_codes if item not in actual_warning_codes]
    if missing_warning_codes:
        failures.append(f"missing warning codes: {', '.join(missing_warning_codes)}")

    required_failure_codes = [str(item) for item in expected.get("required_failure_codes", [])]
    missing_failure_codes = [item for item in required_failure_codes if item not in actual_failure_codes]
    if missing_failure_codes:
        failures.append(f"missing failure codes: {', '.join(missing_failure_codes)}")
    return failures


def _compare_required_values(*, label: str, expected: list[Any], actual: list[Any]) -> list[str]:
    expected_values = [str(value) for value in expected]
    actual_values = [str(value) for value in actual]
    missing = [value for value in expected_values if value not in actual_values]
    if missing:
        return [f"missing {label}: {', '.join(missing)}"]
    return []


def _compare_forbidden_values(*, label: str, expected: list[Any], actual: list[Any]) -> list[str]:
    forbidden_values = [str(value) for value in expected]
    actual_values = [str(value) for value in actual]
    found = [value for value in forbidden_values if value in actual_values]
    if found:
        return [f"found forbidden {label}: {', '.join(found)}"]
    return []


def _compare_tokens(*, rendered_text: str, required_tokens: list[Any], forbidden_tokens: list[Any]) -> list[str]:
    failures: list[str] = []
    for token in [str(item) for item in required_tokens]:
        if token and token not in rendered_text:
            failures.append(f"missing required token: {token}")
    for token in [str(item) for item in forbidden_tokens]:
        if token and token in rendered_text:
            failures.append(f"found forbidden token: {token}")
    return failures


def _normalize_codes(codes: list[str]) -> list[str]:
    mapping = {
        "RISK_QA_CITATION_NOT_IN_SELECTED_EVIDENCE": "RISK_QA_CITATION_INVALID",
        "RISK_QA_CITATION_INVALID_SOURCE": "RISK_QA_CITATION_INVALID",
        "RISK_QA_CITATION_PAGE_MISSING": "RISK_QA_CITATION_METADATA_INCOMPLETE",
        "RISK_QA_INSUFFICIENT_EVIDENCE": "RISK_QA_EVIDENCE_INSUFFICIENT",
        "RISK_QA_LOW_RETRIEVAL_CONFIDENCE": "RISK_QA_EVIDENCE_INSUFFICIENT",
        "RISK_QA_PARTIAL_EVIDENCE": "RISK_QA_EVIDENCE_INSUFFICIENT",
        "RISK_QA_CONTEXT_SOURCE_BLOCKED": "RISK_QA_SOURCE_BOUNDARY_VIOLATION",
    }
    normalized: list[str] = []
    for code in codes:
        normalized_code = mapping.get(str(code), str(code))
        if normalized_code not in normalized:
            normalized.append(normalized_code)
    return normalized


def _pass_rate(results: list[EvalResult]) -> float:
    if not results:
        return 1.0
    return round(sum(1 for result in results if result.passed) / len(results), 6)


def _ratio(results: list[EvalResult], predicate) -> float:
    if not results:
        return 1.0
    return round(sum(1 for result in results if predicate(result)) / len(results), 6)
