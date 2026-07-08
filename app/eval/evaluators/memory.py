"""Memory governance evaluator backed by M4 runtime seams."""

from __future__ import annotations

from typing import Any

from app.eval.evaluators.base import BaseEvaluator
from app.eval.schemas import EvalCase, EvalResult
from app.services.memory.adapters import (
    approved_sql_to_memory_candidate,
    failed_sql_to_memory_candidate,
    risk_qa_answer_to_memory_candidate,
)
from app.services.memory.candidates import MemoryCandidate
from app.services.memory.context_builder import build_memory_context_bundle
from app.services.memory.contracts import (
    MemoryAuthorityLevel,
    MemorySourceType,
    MemoryUsePurpose,
)
from app.services.memory.isolation import validate_memory_use
from app.services.memory.policy import (
    get_allowed_memory_use,
    get_forbidden_memory_use,
)
from app.services.memory.promotion import (
    MemoryPromotionTarget,
    promotion_request_from_candidate,
    validate_memory_promotion,
)
from app.services.memory.retrieval import (
    MemoryRetrievalRequest,
    MemoryRetrievalResult,
    MemoryRetrievalService,
)
from app.services.memory.retrieval_adapter import (
    InMemoryMemoryRetrievalAdapter,
    MemoryStoredRecord,
)
from app.services.memory.retrieval_policy import MemoryRetrievalTaskType


class MemoryGovernanceEvaluator(BaseEvaluator):
    def evaluate_case(self, case: EvalCase) -> EvalResult:
        check_kind = str(case.input.get("check_kind") or "").strip()
        if check_kind == "use_policy":
            return self._evaluate_use_policy(case)
        if check_kind == "retrieval_policy":
            return self._evaluate_retrieval_policy(case)
        if check_kind == "context_rendering":
            return self._evaluate_context_rendering(case)
        if check_kind == "promotion_policy":
            return self._evaluate_promotion_policy(case)
        raise ValueError(f"unsupported memory governance check_kind: {check_kind}")

    def build_suite_metrics(self, results: list[EvalResult]) -> dict[str, Any]:
        total = len(results)
        use_policy_results = [result for result in results if result.metrics.get("check_kind") == "use_policy"]
        retrieval_results = [result for result in results if result.metrics.get("check_kind") == "retrieval_policy"]
        promotion_results = [result for result in results if result.metrics.get("check_kind") == "promotion_policy"]
        context_results = [result for result in results if result.metrics.get("check_kind") == "context_rendering"]
        blocked_use_results = [
            result
            for result in use_policy_results
            if result.metrics.get("expected_decision") == "blocked"
        ]
        allowed_use_results = [
            result
            for result in use_policy_results
            if result.metrics.get("expected_decision") == "allowed"
        ]
        return {
            "memory_governance_pass_rate": _pass_rate(results),
            "isolation_block_accuracy": _pass_rate(blocked_use_results),
            "allowed_use_pass_rate": _pass_rate(allowed_use_results),
            "retrieval_boundary_pass_rate": _pass_rate(retrieval_results),
            "promotion_policy_pass_rate": _pass_rate(promotion_results),
            "context_provenance_coverage": _pass_rate(context_results),
            "total_cases": total,
        }

    def _evaluate_use_policy(self, case: EvalCase) -> EvalResult:
        candidate = _build_candidate_from_case_input(case.input)
        requested_use = MemoryUsePurpose(str(case.input["requested_use"]))
        decision = validate_memory_use(candidate, requested_use)
        actual_decision = "allowed" if decision.allowed else "blocked"
        raw_reason_code = decision.blocked_by
        normalized_reason_code = _normalize_reason_code(raw_reason_code)

        failures = _compare_common_expectations(
            expected=case.expected,
            actual_decision=actual_decision,
            actual_reason_code=normalized_reason_code,
        )
        return _build_result(
            case=case,
            check_kind="use_policy",
            failures=failures,
            metrics={
                "check_kind": "use_policy",
                "expected_decision": case.expected.get("decision"),
                "actual_decision": actual_decision,
                "expected_reason_code": case.expected.get("reason_code"),
                "actual_reason_code": normalized_reason_code,
                "decision_match": not failures,
            },
            artifacts={
                "policy_source": "runtime",
                "raw_decision": actual_decision,
                "raw_reason_code": raw_reason_code,
                "normalized_reason_code": normalized_reason_code,
                "check_kind": "use_policy",
                "memory_source_type": candidate.memory_source_type.value,
                "authority_level": candidate.authority_level.value,
                "requested_use": requested_use.value,
            },
        )

    def _evaluate_retrieval_policy(self, case: EvalCase) -> EvalResult:
        retrieval_result = _run_retrieval_case(case.input)
        returned_memory_ids = [item.memory_id for item in retrieval_result.items]
        rejected_memory_ids = [item.memory_id for item in retrieval_result.rejected_items]
        actual_decision = "blocked" if rejected_memory_ids else "allowed"
        raw_reason_code = retrieval_result.rejected_items[0].blocked_by if retrieval_result.rejected_items else None
        normalized_reason_code = _normalize_reason_code(raw_reason_code)

        failures = _compare_common_expectations(
            expected=case.expected,
            actual_decision=actual_decision,
            actual_reason_code=normalized_reason_code,
        )
        if "returned_memory_ids" in case.expected:
            failures.extend(
                _compare_sequence(
                    "returned_memory_ids",
                    expected=case.expected.get("returned_memory_ids", []),
                    actual=returned_memory_ids,
                )
            )
        if "rejected_memory_ids" in case.expected:
            failures.extend(
                _compare_sequence(
                    "rejected_memory_ids",
                    expected=case.expected.get("rejected_memory_ids", []),
                    actual=rejected_memory_ids,
                )
            )

        return _build_result(
            case=case,
            check_kind="retrieval_policy",
            failures=failures,
            metrics={
                "check_kind": "retrieval_policy",
                "expected_decision": case.expected.get("decision"),
                "actual_decision": actual_decision,
                "expected_reason_code": case.expected.get("reason_code"),
                "actual_reason_code": normalized_reason_code,
                "decision_match": not failures,
            },
            artifacts={
                "policy_source": "adapter",
                "raw_decision": actual_decision,
                "raw_reason_code": raw_reason_code,
                "normalized_reason_code": normalized_reason_code,
                "check_kind": "retrieval_policy",
                "returned_memory_ids": returned_memory_ids,
                "rejected_memory_ids": rejected_memory_ids,
                "retrieval_warnings": list(retrieval_result.warnings),
                "retrieval_metadata": dict(retrieval_result.metadata),
            },
        )

    def _evaluate_context_rendering(self, case: EvalCase) -> EvalResult:
        retrieval_result = _run_retrieval_case(case.input)
        bundle = build_memory_context_bundle(
            retrieval_result,
            max_chars=int(case.input.get("max_chars") or 4000),
        )
        actual_decision = "allowed"
        raw_reason_code = None
        normalized_reason_code = None
        returned_memory_ids = [item.memory_id for item in bundle.items]
        warning_codes = list(bundle.warnings)

        failures = _compare_common_expectations(
            expected=case.expected,
            actual_decision=actual_decision,
            actual_reason_code=normalized_reason_code,
        )
        if "returned_memory_ids" in case.expected:
            failures.extend(
                _compare_sequence(
                    "returned_memory_ids",
                    expected=case.expected.get("returned_memory_ids", []),
                    actual=returned_memory_ids,
                )
            )
        if "required_warning_codes" in case.expected:
            failures.extend(
                _compare_sequence(
                    "required_warning_codes",
                    expected=case.expected.get("required_warning_codes", []),
                    actual=warning_codes,
                    allow_superset=True,
                )
            )
        failures.extend(
            _compare_tokens(
                rendered_text=bundle.rendered_text,
                required_tokens=case.expected.get("required_render_tokens", []),
                forbidden_tokens=case.expected.get("forbidden_render_tokens", []),
            )
        )

        return _build_result(
            case=case,
            check_kind="context_rendering",
            failures=failures,
            metrics={
                "check_kind": "context_rendering",
                "expected_decision": case.expected.get("decision"),
                "actual_decision": actual_decision,
                "expected_reason_code": case.expected.get("reason_code"),
                "actual_reason_code": normalized_reason_code,
                "decision_match": not failures,
            },
            artifacts={
                "policy_source": "adapter",
                "raw_decision": actual_decision,
                "raw_reason_code": raw_reason_code,
                "normalized_reason_code": normalized_reason_code,
                "check_kind": "context_rendering",
                "returned_memory_ids": returned_memory_ids,
                "warning_codes": warning_codes,
                "rendered_text": bundle.rendered_text,
                "context_metadata": dict(bundle.metadata),
            },
        )

    def _evaluate_promotion_policy(self, case: EvalCase) -> EvalResult:
        candidate = _build_candidate_from_case_input(case.input)
        target = MemoryPromotionTarget(str(case.input["target"]))
        request = promotion_request_from_candidate(candidate, target)
        decision = validate_memory_promotion(request)
        actual_decision = "allowed" if decision.allowed else "blocked"
        raw_reason_code = decision.blocked_by.value if decision.blocked_by is not None else None
        normalized_reason_code = _normalize_reason_code(raw_reason_code)

        failures = _compare_common_expectations(
            expected=case.expected,
            actual_decision=actual_decision,
            actual_reason_code=normalized_reason_code,
        )
        return _build_result(
            case=case,
            check_kind="promotion_policy",
            failures=failures,
            metrics={
                "check_kind": "promotion_policy",
                "expected_decision": case.expected.get("decision"),
                "actual_decision": actual_decision,
                "expected_reason_code": case.expected.get("reason_code"),
                "actual_reason_code": normalized_reason_code,
                "decision_match": not failures,
            },
            artifacts={
                "policy_source": "runtime",
                "raw_decision": actual_decision,
                "raw_reason_code": raw_reason_code,
                "normalized_reason_code": normalized_reason_code,
                "check_kind": "promotion_policy",
                "promotion_target": target.value,
                "memory_source_type": candidate.memory_source_type.value,
                "authority_level": candidate.authority_level.value,
            },
        )


def _build_candidate_from_case_input(payload: dict[str, Any]) -> MemoryCandidate:
    source_type = MemorySourceType(str(payload["source_type"]))
    authority_level = MemoryAuthorityLevel(str(payload["authority_level"]))
    content = str(payload.get("content") or f"Synthetic {source_type.value} memory.")
    user_id = str(payload.get("user_id") or "u1")
    project_id = str(payload.get("project_id") or "p1")
    country = str(payload.get("country") or "mx")

    if source_type is MemorySourceType.RISK_QA_ANSWER:
        citations = [{"doc_id": "doc-1"}] if authority_level is not MemoryAuthorityLevel.UNVERIFIED else None
        return risk_qa_answer_to_memory_candidate(
            answer=content,
            question="Synthetic risk QA question",
            citations=citations,
            user_id=user_id,
            project_id=project_id,
            country=country,
            source_run_id="eval-memory-risk-qa",
        )

    if source_type is MemorySourceType.DATA_AGENT_SQL_CASE:
        if authority_level is MemoryAuthorityLevel.HUMAN_APPROVED:
            return approved_sql_to_memory_candidate(
                sql="select 1",
                question="Synthetic approved SQL",
                approved_sql_hash="approved-sql-hash",
                user_id=user_id,
                project_id=project_id,
                country=country,
                source_run_id="eval-memory-approved-sql",
            )
        return MemoryCandidate(
            content=content,
            memory_source_type=source_type,
            authority_level=authority_level,
            allowed_memory_use=get_allowed_memory_use(source_type),
            forbidden_memory_use=get_forbidden_memory_use(source_type),
            user_id=user_id,
            project_id=project_id,
            country=country,
            source_run_id="eval-memory-sql-case",
        )

    if source_type is MemorySourceType.DATA_AGENT_SQL_ERROR:
        return failed_sql_to_memory_candidate(
            sql="select * from missing_table",
            error="table not found",
            question="Synthetic broken SQL",
            user_id=user_id,
            project_id=project_id,
            country=country,
            source_run_id="eval-memory-sql-error",
        )

    return MemoryCandidate(
        content=content,
        memory_source_type=source_type,
        authority_level=authority_level,
        allowed_memory_use=get_allowed_memory_use(source_type),
        forbidden_memory_use=get_forbidden_memory_use(source_type),
        user_id=user_id,
        project_id=project_id,
        country=country,
        source_run_id=f"eval-memory-{source_type.value}",
        evidence_status=str(payload.get("evidence_status") or "") or None,
    )


def _run_retrieval_case(payload: dict[str, Any]) -> MemoryRetrievalResult:
    request_payload = dict(payload.get("request") or {})
    request = MemoryRetrievalRequest(
        query=str(request_payload["query"]),
        task_type=MemoryRetrievalTaskType(str(request_payload["task_type"])),
        user_id=str(request_payload["user_id"]),
        project_id=str(request_payload.get("project_id") or "") or None,
        country=str(request_payload.get("country") or "") or None,
        session_id=str(request_payload.get("session_id") or "") or None,
        max_items=int(request_payload.get("max_items") or 8),
        include_legacy_memory=bool(request_payload.get("include_legacy_memory", False)),
        production_context=bool(request_payload.get("production_context", False)),
    )
    records = [_build_stored_record(record_payload) for record_payload in payload.get("records", [])]
    service = MemoryRetrievalService(InMemoryMemoryRetrievalAdapter(records=records))
    return service.retrieve(request)


def _build_stored_record(payload: dict[str, Any]) -> MemoryStoredRecord:
    source_type = MemorySourceType(str(payload["source_type"]))
    authority_level = MemoryAuthorityLevel(str(payload["authority_level"]))
    allowed_uses = [MemoryUsePurpose(str(value)) for value in payload.get("allowed_uses", [])]
    forbidden_uses = [MemoryUsePurpose(str(value)) for value in payload.get("forbidden_uses", [])]
    memory_id = str(payload["memory_id"])
    return MemoryStoredRecord(
        memory_id=memory_id,
        content=str(payload.get("content") or f"Synthetic {source_type.value} memory."),
        user_id=str(payload.get("user_id") or "u1"),
        project_id=str(payload.get("project_id") or "p1") or None,
        country=str(payload.get("country") or "mx") or None,
        status=str(payload.get("status") or "active"),
        metadata_json={
            "m4_contract_version": "m4-2",
            "memory_source_type": source_type.value,
            "authority_level": authority_level.value,
            "allowed_memory_use": [item.value for item in allowed_uses],
            "forbidden_memory_use": [item.value for item in forbidden_uses],
            "source_run_id": str(payload.get("source_run_id") or f"run-{memory_id}"),
            "source_artifact_id": str(payload.get("source_artifact_id") or f"artifact-{memory_id}"),
            "evidence_status": str(payload.get("evidence_status") or "") or None,
            "candidate_metadata": dict(payload.get("candidate_metadata") or {"label": memory_id}),
            "scope_warnings": list(payload.get("scope_warnings") or []),
            "write_gate": dict(
                payload.get(
                    "write_gate",
                    {
                        "status": "accepted",
                        "reject_reason": None,
                        "redacted": False,
                        "dedupe_key": f"dedupe-{memory_id}",
                        "decision_reason": "accepted",
                    },
                )
            ),
        },
        importance=float(payload.get("importance") or 0.5),
        confidence=float(payload.get("confidence") or 0.5),
        created_at=str(payload.get("created_at") or "2026-07-07T00:00:00+00:00") or None,
    )


def _compare_common_expectations(
    *,
    expected: dict[str, Any],
    actual_decision: str,
    actual_reason_code: str | None,
) -> list[str]:
    failures: list[str] = []
    expected_decision = str(expected.get("decision") or "").strip()
    if expected_decision and actual_decision != expected_decision:
        failures.append(f"expected decision {expected_decision} but got {actual_decision}")

    expected_reason_code = str(expected.get("reason_code") or "").strip() or None
    if expected_reason_code != actual_reason_code:
        if expected_reason_code or actual_reason_code:
            failures.append(
                f"expected reason_code {expected_reason_code or 'none'} "
                f"but got {actual_reason_code or 'none'}"
            )
    return failures


def _compare_sequence(
    label: str,
    *,
    expected: list[Any],
    actual: list[Any],
    allow_superset: bool = False,
) -> list[str]:
    expected_values = [str(value) for value in expected]
    actual_values = [str(value) for value in actual]
    if not expected_values and not actual_values:
        return []
    if allow_superset:
        missing_values = [value for value in expected_values if value not in actual_values]
        if missing_values:
            return [f"missing {label}: {', '.join(missing_values)}"]
        return []
    if expected_values != actual_values:
        return [f"expected {label} {expected_values} but got {actual_values}"]
    return []


def _compare_tokens(
    *,
    rendered_text: str,
    required_tokens: list[Any],
    forbidden_tokens: list[Any],
) -> list[str]:
    failures: list[str] = []
    for token in [str(value) for value in required_tokens]:
        if token not in rendered_text:
            failures.append(f"missing required render token: {token}")
    for token in [str(value) for value in forbidden_tokens]:
        if token in rendered_text:
            failures.append(f"found forbidden render token: {token}")
    return failures


def _build_result(
    *,
    case: EvalCase,
    check_kind: str,
    failures: list[str],
    metrics: dict[str, Any],
    artifacts: dict[str, Any],
) -> EvalResult:
    return EvalResult(
        case_id=case.case_id,
        suite=case.suite,
        status="PASS" if not failures else "FAIL",
        passed=not failures,
        score=1.0 if not failures else 0.0,
        metrics=metrics,
        failures=failures,
        artifacts=artifacts,
        warnings=[],
    )


def _normalize_reason_code(raw_reason_code: str | None) -> str | None:
    if raw_reason_code is None:
        return None
    mapping = {
        "explicit_forbidden_use": "MEMORY_USE_FORBIDDEN",
        "not_in_allowed_use": "MEMORY_USE_NOT_ALLOWED",
        "authority_level_insufficient": "APPROVAL_REQUIRED",
        "unverified_production_grounding": "APPROVAL_REQUIRED",
        "audit_only_non_audit_use": "AUDIT_CONTEXT_RESTRICTED",
        "human_approval_required": "APPROVAL_REQUIRED",
        "explicitly_forbidden": "PROMOTION_FORBIDDEN",
        "source_type_not_allowed": "PROMOTION_FORBIDDEN",
        "evidence_insufficient": "EVIDENCE_REQUIRED",
        "target_requires_governance_workflow": "GOVERNANCE_WORKFLOW_REQUIRED",
        "unknown_target": "UNKNOWN_TARGET",
        "malformed_m4_metadata": "MALFORMED_MEMORY_METADATA",
        "inactive_memory_status": "INACTIVE_MEMORY_STATUS",
        "project_id_mismatch": "SCOPE_MISMATCH",
        "country_mismatch": "SCOPE_MISMATCH",
    }
    return mapping.get(raw_reason_code, str(raw_reason_code).upper())


def _pass_rate(results: list[EvalResult]) -> float:
    if not results:
        return 1.0
    return round(sum(1 for result in results if result.passed) / len(results), 6)
