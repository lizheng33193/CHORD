"""Data Agent regression evaluator backed by deterministic runtime seams."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.data_agent.plan_review import review_sql_against_intent_plan
from app.data_agent.repair import select_repairable_plan_warnings
from app.data_agent.safety import run_sql_safety_gate
from app.data_agent.semantic_validation import (
    SqlSemanticValidationRequest,
    validate_sql_semantics,
)
from app.data_agent.service import _review_sql_candidate
from app.data_agent.sql_plan import SqlIntentPlan, validate_structured_sql_plan
from app.eval.evaluators.base import BaseEvaluator
from app.eval.schemas import EvalCase, EvalResult


class DataAgentEvaluator(BaseEvaluator):
    def evaluate_case(self, case: EvalCase) -> EvalResult:
        check_kind = str(case.input.get("check_kind") or "").strip()
        if check_kind == "plan_contract":
            return self._evaluate_plan_contract(case)
        if check_kind == "plan_validation":
            return self._evaluate_plan_validation(case)
        if check_kind == "safety_review":
            return self._evaluate_safety_review(case)
        if check_kind == "semantic_validation":
            return self._evaluate_semantic_validation(case)
        if check_kind in {"field_grounding", "canonical_review"}:
            return self._evaluate_grounding_review(case)
        if check_kind == "plan_consistency":
            return self._evaluate_plan_consistency(case)
        if check_kind == "repair_policy":
            return self._evaluate_repair_policy(case)
        if check_kind == "hitl_boundary":
            return self._evaluate_hitl_boundary(case)
        if check_kind == "sql_case_policy":
            return self._evaluate_sql_case_policy(case)
        raise ValueError(f"unsupported data agent check_kind: {check_kind}")

    def build_suite_metrics(self, results: list[EvalResult]) -> dict[str, Any]:
        suite_id = results[0].suite if results else "data_agent"
        metrics: dict[str, Any] = {
            f"{suite_id}_pass_rate": _pass_rate(results),
            "dangerous_sql_block_accuracy": _pass_rate(
                [
                    result
                    for result in results
                    if "DANGEROUS_SQL_BLOCKED" in list(result.metrics.get("expected_failure_codes") or [])
                ]
            ),
            "plan_validation_pass_rate": _pass_rate(
                [
                    result
                    for result in results
                    if result.metrics.get("check_kind") in {"plan_contract", "plan_validation"}
                ]
            ),
            "grounding_warning_accuracy": _pass_rate(
                [
                    result
                    for result in results
                    if result.metrics.get("check_kind") in {"field_grounding", "canonical_review", "plan_consistency"}
                ]
            ),
            "semantic_validation_block_accuracy": _pass_rate(
                [
                    result
                    for result in results
                    if result.metrics.get("check_kind") == "semantic_validation"
                ]
            ),
            "hitl_boundary_pass_rate": _pass_rate(
                [
                    result
                    for result in results
                    if result.metrics.get("check_kind") == "hitl_boundary"
                ]
            ),
            "sql_case_policy_pass_rate": _pass_rate(
                [
                    result
                    for result in results
                    if result.metrics.get("check_kind") == "sql_case_policy"
                ]
            ),
        }
        return metrics

    def _evaluate_plan_contract(self, case: EvalCase) -> EvalResult:
        raw_failures: list[str] = []
        raw_warnings: list[str] = []
        actual_tables: list[str] = []
        actual_fields: list[str] = []
        try:
            plan = SqlIntentPlan.model_validate(dict(case.input.get("structured_sql_plan") or {}))
            actual_decision = "allowed"
            actual_tables = list(plan.source_tables)
            actual_fields = list(plan.required_fields)
        except ValidationError:
            actual_decision = "blocked"
            raw_failures = ["DATA_AGENT_SQL_PLAN_INVALID"]

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
                label="tables",
                expected=case.expected.get("must_include_tables", []),
                actual=actual_tables,
            )
        )
        failures.extend(
            _compare_required_values(
                label="fields",
                expected=case.expected.get("must_include_fields", []),
                actual=actual_fields,
            )
        )
        failures.extend(
            _compare_forbidden_values(
                label="fields",
                expected=case.expected.get("must_not_include_fields", []),
                actual=actual_fields,
            )
        )
        return _build_result(
            case=case,
            check_kind="plan_contract",
            actual_decision=actual_decision,
            raw_warnings=raw_warnings,
            normalized_warnings=normalized_warnings,
            raw_failures=raw_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "adapter",
                "check_kind": "plan_contract",
                "raw_decision": actual_decision,
                "plan_tables": actual_tables,
                "plan_fields": actual_fields,
            },
        )

    def _evaluate_plan_validation(self, case: EvalCase) -> EvalResult:
        plan = SqlIntentPlan.model_validate(dict(case.input.get("structured_sql_plan") or {}))
        validation = validate_structured_sql_plan(
            plan=plan,
            retrieval_snapshot=dict(case.input.get("retrieval_snapshot") or {}),
        )
        actual_decision = "allowed" if validation.valid else "blocked"
        raw_failures = [validation.code] if validation.code else []
        raw_warnings: list[str] = []
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
            check_kind="plan_validation",
            actual_decision=actual_decision,
            raw_warnings=raw_warnings,
            normalized_warnings=normalized_warnings,
            raw_failures=raw_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "runtime",
                "check_kind": "plan_validation",
                "raw_decision": actual_decision,
                "plan_validation": validation.model_dump(mode="json"),
            },
        )

    def _evaluate_safety_review(self, case: EvalCase) -> EvalResult:
        sql = str(case.input.get("sql") or "")
        safety_result = run_sql_safety_gate(
            sql,
            str(case.input.get("sql_kind") or "query_only"),
            str(case.input.get("country") or "mx"),
        )
        actual_decision = _safety_status_to_decision(str(safety_result.get("status") or "passed"))
        raw_failures = _derive_safety_failure_codes(safety_result=safety_result, sql=sql)
        raw_warnings = _derive_safety_warning_codes(safety_result=safety_result)
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
            check_kind="safety_review",
            actual_decision=actual_decision,
            raw_warnings=raw_warnings,
            normalized_warnings=normalized_warnings,
            raw_failures=raw_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "runtime",
                "check_kind": "safety_review",
                "raw_decision": str(safety_result.get("status") or "passed"),
                "safety_result": dict(safety_result),
                "requires_human_review": safety_result.get("status") == "review_only",
            },
        )

    def _evaluate_semantic_validation(self, case: EvalCase) -> EvalResult:
        result = validate_sql_semantics(
            SqlSemanticValidationRequest(
                query=str(case.input.get("request_text") or ""),
                sql=str(case.input.get("sql") or ""),
                structured_sql_plan=dict(case.input.get("structured_sql_plan") or {}),
                business_context={
                    "run_type": case.input.get("run_type"),
                    "output_bucket": case.input.get("output_bucket"),
                },
                expected_country=str(case.input.get("country") or "") or None,
                expected_time_window=str((case.input.get("metadata") or {}).get("expected_time_window") or "") or None,
                allowed_tables=list((case.input.get("metadata") or {}).get("catalog_tables") or []),
                canonical_field_policy_refs=dict((case.input.get("metadata") or {}).get("canonical_field_policy_refs") or {}),
            )
        )
        raw_failures = [violation.code for violation in result.violations if violation.blocking]
        raw_warnings = [violation.code for violation in result.violations if not violation.blocking]
        actual_decision = _semantic_status_to_decision(result.validation_status)
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
            check_kind="semantic_validation",
            actual_decision=actual_decision,
            raw_warnings=raw_warnings,
            normalized_warnings=normalized_warnings,
            raw_failures=raw_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "runtime",
                "check_kind": "semantic_validation",
                "raw_decision": result.validation_status,
                "requires_human_review": result.requires_human_review,
                "semantic_validation": result.model_dump(mode="json"),
            },
        )

    def _evaluate_grounding_review(self, case: EvalCase) -> EvalResult:
        review = _review_sql_candidate(
            sql_text=str(case.input.get("sql") or ""),
            sql_kind=str(case.input.get("sql_kind") or "query_only"),
            target_country=str(case.input.get("country") or "mx"),
            retrieval_snapshot=dict(case.input.get("retrieval_snapshot") or {}),
            natural_language_request=str(case.input.get("request_text") or ""),
            run_type=str(case.input.get("run_type") or "cohort_query"),
            output_bucket=str(case.input.get("output_bucket") or "") or None,
        )
        raw_warnings = [
            str(item.get("category") or "").strip()
            for item in list(review.get("warnings") or [])
            if str(item.get("category") or "").strip()
        ]
        raw_failures = _derive_review_failure_codes(review)
        actual_decision = _review_result_to_decision(review)
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
            check_kind=str(case.input.get("check_kind") or "field_grounding"),
            actual_decision=actual_decision,
            raw_warnings=raw_warnings,
            normalized_warnings=normalized_warnings,
            raw_failures=raw_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "adapter",
                "check_kind": str(case.input.get("check_kind") or "field_grounding"),
                "raw_decision": str(review.get("status") or "passed"),
                "safety_result": dict(review),
                "requires_human_review": bool(review.get("semantic_validation", {}).get("requires_human_review")),
            },
        )

    def _evaluate_plan_consistency(self, case: EvalCase) -> EvalResult:
        warnings = review_sql_against_intent_plan(
            sql_text=str(case.input.get("sql") or ""),
            retrieval_snapshot=dict(case.input.get("retrieval_snapshot") or {}),
            natural_language_request=str(case.input.get("request_text") or ""),
            run_type=str(case.input.get("run_type") or "cohort_query"),
            output_bucket=str(case.input.get("output_bucket") or "") or None,
        )
        raw_warnings = [
            str(item.get("category") or "").strip()
            for item in warnings
            if str(item.get("category") or "").strip()
        ]
        raw_failures: list[str] = []
        actual_decision = "warning" if raw_warnings else "allowed"
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
            check_kind="plan_consistency",
            actual_decision=actual_decision,
            raw_warnings=raw_warnings,
            normalized_warnings=normalized_warnings,
            raw_failures=raw_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "runtime",
                "check_kind": "plan_consistency",
                "raw_decision": actual_decision,
                "raw_warning_details": warnings,
            },
        )

    def _evaluate_repair_policy(self, case: EvalCase) -> EvalResult:
        selected = select_repairable_plan_warnings(list((case.input.get("metadata") or {}).get("plan_warnings") or []))
        raw_warnings = [
            str(item.get("category") or "").strip()
            for item in selected
            if str(item.get("category") or "").strip()
        ]
        raw_failures: list[str] = []
        actual_decision = "allowed" if selected else "warning"
        normalized_failures = _normalize_codes(raw_failures)
        normalized_warnings = _normalize_codes(raw_warnings)
        failures = _compare_common_expectations(
            expected=case.expected,
            actual_decision=actual_decision,
            actual_warning_codes=normalized_warnings,
            actual_failure_codes=normalized_failures,
        )
        if "repair_allowed" in case.expected:
            repair_allowed = bool(selected)
            if repair_allowed != bool(case.expected.get("repair_allowed")):
                failures.append(
                    f"expected repair_allowed {case.expected.get('repair_allowed')} but got {repair_allowed}"
                )
        return _build_result(
            case=case,
            check_kind="repair_policy",
            actual_decision=actual_decision,
            raw_warnings=raw_warnings,
            normalized_warnings=normalized_warnings,
            raw_failures=raw_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "runtime",
                "check_kind": "repair_policy",
                "raw_decision": actual_decision,
                "repairable_warnings": selected,
            },
        )

    def _evaluate_hitl_boundary(self, case: EvalCase) -> EvalResult:
        metadata = dict(case.input.get("metadata") or {})
        action = str(metadata.get("action") or "execute")
        current_sql_kind = str(metadata.get("current_sql_kind") or "query_only")
        current_safety_status = str(metadata.get("current_safety_status") or "blocked")
        current_sql_hash = str(metadata.get("current_sql_hash") or "")
        approved_sql_hash = str(metadata.get("approved_sql_hash") or "")
        current_sql_version_id = metadata.get("current_sql_version_id")
        approved_sql_version_id = metadata.get("approved_sql_version_id")

        approval_allowed = current_sql_kind == "query_only" and current_safety_status == "passed"
        execute_allowed = (
            bool(current_sql_version_id)
            and bool(approved_sql_version_id)
            and bool(approved_sql_hash)
            and current_sql_hash == approved_sql_hash
            and current_sql_version_id == approved_sql_version_id
            and current_sql_kind == "query_only"
            and current_safety_status == "passed"
        )
        raw_failures: list[str] = []
        if action == "approve" and not approval_allowed:
            actual_decision = "blocked"
        elif action == "execute" and not execute_allowed:
            actual_decision = "blocked"
            raw_failures.append("SQL_APPROVAL_REQUIRED")
        else:
            actual_decision = "allowed"

        normalized_failures = _normalize_codes(raw_failures)
        normalized_warnings: list[str] = []
        failures = _compare_common_expectations(
            expected=case.expected,
            actual_decision=actual_decision,
            actual_warning_codes=normalized_warnings,
            actual_failure_codes=normalized_failures,
        )
        if "execute_allowed" in case.expected:
            if execute_allowed != bool(case.expected.get("execute_allowed")):
                failures.append(
                    f"expected execute_allowed {case.expected.get('execute_allowed')} but got {execute_allowed}"
                )
        if "repair_allowed" in case.expected:
            repair_allowed = bool(metadata.get("repaired"))
            if repair_allowed != bool(case.expected.get("repair_allowed")):
                failures.append(
                    f"expected repair_allowed {case.expected.get('repair_allowed')} but got {repair_allowed}"
                )
        return _build_result(
            case=case,
            check_kind="hitl_boundary",
            actual_decision=actual_decision,
            raw_warnings=[],
            normalized_warnings=[],
            raw_failures=raw_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "adapter",
                "check_kind": "hitl_boundary",
                "raw_decision": actual_decision,
                "approval_allowed": approval_allowed,
                "execute_allowed": execute_allowed,
                "approved_sql_hash": approved_sql_hash or None,
            },
        )

    def _evaluate_sql_case_policy(self, case: EvalCase) -> EvalResult:
        metadata = dict(case.input.get("metadata") or {})
        execution_status = str(metadata.get("execution_status") or "")
        current_sql_hash = str(metadata.get("current_sql_hash") or "")
        approved_sql_hash = str(metadata.get("approved_sql_hash") or "")
        approved_example_eligible = (
            execution_status == "executed"
            and bool(current_sql_hash)
            and bool(approved_sql_hash)
            and current_sql_hash == approved_sql_hash
        )
        error_case_eligible = execution_status == "failed" and bool(str(metadata.get("error_message") or "").strip())

        raw_failures: list[str] = []
        if error_case_eligible and not approved_example_eligible:
            actual_decision = "warning"
            raw_failures.append("FAILED_SQL_CASE_NOT_APPROVED")
        elif approved_example_eligible:
            actual_decision = "allowed"
        else:
            actual_decision = "blocked"
            raw_failures.append("APPROVED_SQL_CASE_REQUIRED")

        normalized_failures = _normalize_codes(raw_failures)
        normalized_warnings: list[str] = []
        failures = _compare_common_expectations(
            expected=case.expected,
            actual_decision=actual_decision,
            actual_warning_codes=normalized_warnings,
            actual_failure_codes=normalized_failures,
        )
        if "must_reference_approved_case" in case.expected:
            expected = bool(case.expected.get("must_reference_approved_case"))
            if approved_example_eligible != expected:
                failures.append(
                    f"expected must_reference_approved_case {expected} but got {approved_example_eligible}"
                )
        if bool(case.expected.get("must_not_reference_failed_case", False)) and error_case_eligible:
            failures.append("expected failed-case reference to remain disabled")
        return _build_result(
            case=case,
            check_kind="sql_case_policy",
            actual_decision=actual_decision,
            raw_warnings=[],
            normalized_warnings=[],
            raw_failures=raw_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "adapter",
                "check_kind": "sql_case_policy",
                "raw_decision": actual_decision,
                "approved_sql_hash": approved_sql_hash or None,
                "approved_example_eligible": approved_example_eligible,
                "error_case_eligible": error_case_eligible,
            },
        )


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
        warnings=[],
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

    forbidden_warning_codes = [str(item) for item in expected.get("forbidden_warning_codes", [])]
    present_forbidden_warning_codes = [item for item in forbidden_warning_codes if item in actual_warning_codes]
    if present_forbidden_warning_codes:
        failures.append(f"found forbidden warning codes: {', '.join(present_forbidden_warning_codes)}")

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


def _normalize_codes(codes: list[str]) -> list[str]:
    mapping = {
        "RISKY_SQL_OPERATION": "DANGEROUS_SQL_BLOCKED",
        "BROAD_SCAN_RISK": "PLAN_BROAD_SCAN_RISK",
        "UNRESOLVED_PLACEHOLDER": "UNRESOLVED_PLACEHOLDER",
        "UNSUPPORTED_FIELD": "UNSUPPORTED_FIELD",
        "NON_CANONICAL_FIELD": "NON_CANONICAL_FIELD",
        "PLAN_DATE_DRIFT": "PLAN_DATE_DRIFT",
        "PLAN_SOURCE_FILTER_DRIFT": "PLAN_SOURCE_FILTER_DRIFT",
        "PLAN_CANONICAL_FIELD_DRIFT": "PLAN_CANONICAL_FIELD_DRIFT",
        "PLAN_REQUIRED_FIELD_MISSING": "PLAN_REQUIRED_FIELD_MISSING",
        "PLAN_BROAD_SCAN_RISK": "PLAN_BROAD_SCAN_RISK",
        "PLAN_FORBIDDEN_PATTERN": "PLAN_FORBIDDEN_PATTERN",
        "DATA_AGENT_SQL_PLAN_INVALID": "DATA_AGENT_SQL_PLAN_INVALID",
        "DATA_AGENT_WRITEBACK_REQUIRES_COHORT": "DATA_AGENT_WRITEBACK_REQUIRES_COHORT",
        "UID_BOUNDARY_MISSING": "UID_BOUNDARY_MISSING",
        "TIME_WINDOW_UNSPECIFIED": "TIME_WINDOW_UNSPECIFIED",
        "SQL_APPROVAL_REQUIRED": "SQL_APPROVAL_REQUIRED",
        "APPROVED_SQL_CASE_REQUIRED": "APPROVED_SQL_CASE_REQUIRED",
        "FAILED_SQL_CASE_NOT_APPROVED": "FAILED_SQL_CASE_NOT_APPROVED",
    }
    normalized: list[str] = []
    for code in codes:
        normalized_code = mapping.get(str(code), str(code))
        if normalized_code not in normalized:
            normalized.append(normalized_code)
    return normalized


def _safety_status_to_decision(status: str) -> str:
    if status == "passed":
        return "allowed"
    if status == "review_only":
        return "warning"
    return "blocked"


def _semantic_status_to_decision(status: str) -> str:
    if status == "passed":
        return "allowed"
    if status in {"warning", "needs_human_review"}:
        return "warning"
    return "blocked"


def _derive_safety_failure_codes(*, safety_result: dict[str, Any], sql: str) -> list[str]:
    if str(safety_result.get("status") or "") != "blocked":
        return []
    if safety_result.get("rule_category"):
        return [str(safety_result["rule_category"]).strip()]
    lowered_sql = str(sql or "").strip().lower()
    if lowered_sql.startswith(("delete ", "drop ", "truncate ", "alter ", "insert ", "create ", "replace ", "merge ", "update ")):
        return ["RISKY_SQL_OPERATION"]
    return []


def _derive_safety_warning_codes(*, safety_result: dict[str, Any]) -> list[str]:
    if str(safety_result.get("status") or "") == "review_only":
        return ["REVIEW_ONLY"]
    return []


def _derive_review_failure_codes(review: dict[str, Any]) -> list[str]:
    if str(review.get("status") or "") != "blocked":
        return []
    raw_codes: list[str] = []
    for item in list(review.get("blocked_reasons") or []):
        text = str(item or "").strip()
        if "risky write or expansion operation" in text.lower():
            raw_codes.append("RISKY_SQL_OPERATION")
        elif "uid boundary" in text.lower():
            raw_codes.append("UID_BOUNDARY_MISSING")
    return raw_codes


def _review_result_to_decision(review: dict[str, Any]) -> str:
    if str(review.get("status") or "") == "blocked":
        return "blocked"
    if list(review.get("warnings") or []):
        return "warning"
    return "allowed"


def _pass_rate(results: list[EvalResult]) -> float:
    if not results:
        return 1.0
    return round(sum(1 for result in results if result.passed) / len(results), 6)
