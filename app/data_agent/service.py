"""Service layer for Data Agent SQL HITL."""

from __future__ import annotations

import copy
import hashlib
import re
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.auth.permissions import normalize_country_scope_value, require_country_access, require_permissions
from app.core.audit import record_runtime_audit_event
from app.core.user_context import UserContext
from app.data_agent.repair import (
    build_plan_guided_repair_instruction,
    select_repairable_plan_warnings,
)
from app.data_agent.hybrid_runtime import (
    DISCARD_REASON_CANDIDATE_SQL_EMPTY,
    DISCARD_REASON_CANDIDATE_GENERATION_FAILED,
    DISCARD_REASON_POST_SQL_KIND_MISMATCH,
    FINAL_GENERATION_PASS_DETERMINISTIC,
    FINAL_GENERATION_PASS_DETERMINISTIC_RERUN,
    FINAL_GENERATION_PASS_HYBRID_CANDIDATE,
    FINAL_GENERATION_PASS_HYBRID_ENABLED,
    PROMPT_INJECTION_NONE,
    PROMPT_INJECTION_SUPPLEMENTAL_CANDIDATES_V1,
    build_shadow_trace,
    extract_hybrid_audit_summary,
    finalize_shadow_trace_for_sql_kind,
)
from app.data_agent.sql_plan import (
    build_structured_sql_plan,
    validate_structured_sql_plan,
)
from app.data_agent.repository import DataAgentRepository
from app.data_agent.safety import resolve_country_names, run_sql_safety_gate
from app.data_agent.plan_review import review_sql_against_intent_plan
from app.data_knowledge.canonical_fields import normalize_field_name, normalize_table_name
from app.data_agent.schemas import (
    DataAgentEditRequest,
    DataAgentReviseRequest,
    DataAgentRunCreateRequest,
    DataAgentRunDetail,
    DataAgentRunListResponse,
    DataAgentRunSummary,
    ExecutionView,
    ReviewEventView,
    SQLVersionView,
    WritebackView,
)
from app.data_knowledge.prompt_context import PromptContextAssembler, append_prompt_section
from app.data_knowledge.retriever import DataKnowledgeRetriever
from app.data_knowledge.models import DataSqlErrorCase, DataSqlExample
from app.core.config import settings
from data_acquisition_agent.executor import (
    enforce_pre_execution_gates,
    execute_query,
    precheck_row_count,
    run_execute_pipeline,
)
from data_acquisition_agent.manifest import load_manifest
from data_acquisition_agent.orchestrator import OrchestratorError
from data_acquisition_agent.schemas import ExecuteRequest, GenerateRequest, TargetAction, TargetCountry
from data_acquisition_agent.schemas import ErrorType as DataAcquisitionErrorType


_UID_FIELD_CANDIDATES = {"uid", "userid", "useruuid", "customerid"}
_SQL_KEYWORDS = {
    "select", "from", "where", "and", "or", "with", "as", "on", "join", "left", "right", "inner",
    "outer", "full", "group", "by", "order", "limit", "having", "case", "when", "then", "else",
    "end", "distinct", "union", "all", "not", "is", "null", "in", "between", "like", "desc", "asc",
    "true", "false", "over", "partition", "rows", "range", "current_date", "date_sub", "date_add",
    "date_format", "count", "sum", "avg", "min", "max", "cast", "if", "coalesce",
    "interval", "day", "days", "month", "months", "year", "years", "hour", "hours", "minute", "minutes", "second", "seconds",
}
_FIELD_TOKEN_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")
_QUALIFIED_FIELD_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b")
_FROM_JOIN_RE = re.compile(
    r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_.]*)(?:\s+(?:as\s+)?([A-Za-z_][A-Za-z0-9_]*))?",
    re.IGNORECASE,
)
_WITH_CTE_RE = re.compile(r"\bwith\s+([A-Za-z_][A-Za-z0-9_]*)\s+as\s*\(", re.IGNORECASE)
_FUNCTION_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.IGNORECASE)
_AS_ALIAS_RE = re.compile(r"\bas\s+([A-Za-z_][A-Za-z0-9_]*)\b", re.IGNORECASE)
_STRUCTURED_SQL_PLAN_PROVENANCE_KEY = "structured_sql_plan_provenance"
_SOURCE_CONTEXT_DETERMINISTIC_ATTEMPT = "deterministic_attempt"
_SOURCE_CONTEXT_HYBRID_CANDIDATE_ATTEMPT = "hybrid_candidate_attempt"
_SOURCE_CONTEXT_HYBRID_ENABLED_ATTEMPT = "hybrid_enabled_attempt"
_SOURCE_CONTEXT_DETERMINISTIC_RERUN_ATTEMPT = "deterministic_rerun_attempt"


def _normalize_column_name(name: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name or "").strip().lower())


def _generate_sql_response(
    *,
    natural_language_request: str,
    target_country: str,
    target_action: str = "extract",
    knowledge_prompt_context=None,
) -> dict[str, Any]:
    from data_acquisition_agent.orchestrator import DataAcquisitionOrchestrator

    _normalized_country, full_country = resolve_country_names(target_country)
    request = GenerateRequest(
        natural_language_request=natural_language_request,
        target_country=TargetCountry(full_country),
        target_action=TargetAction(target_action),
    )
    response = DataAcquisitionOrchestrator().generate(
        request,
        retrieved_context=knowledge_prompt_context,
    )
    return response.model_dump(mode="json")


def _execute_cohort_query(*, sql_text: str, target_country: str) -> dict[str, Any]:
    from app.core.config import settings
    from data_acquisition_agent.connection import open_starrocks_connection

    _normalized_country, full_country = resolve_country_names(target_country)
    manifest = load_manifest(full_country)
    request_id = uuid.uuid4().hex
    enforce_pre_execution_gates(
        approved_sql=sql_text,
        sql_kind="query_only",
        analyst_private_prefix=manifest.analyst_private_prefix,
        request_id=request_id,
    )
    with open_starrocks_connection(request_id=request_id) as conn:
        rows_estimated = precheck_row_count(
            conn=conn,
            approved_sql=sql_text,
            max_rows=settings.da_max_result_rows,
            timeout_s=settings.da_query_timeout_seconds,
            request_id=request_id,
        )
        df = execute_query(
            conn=conn,
            approved_sql=sql_text,
            timeout_s=settings.da_query_timeout_seconds,
            request_id=request_id,
        )
    uid_column = next((col for col in df.columns if _normalize_column_name(col) in _UID_FIELD_CANDIDATES), None)
    if uid_column is None:
        raise HTTPException(status_code=422, detail="query_data result missing uid column")
    uids = sorted({
        text
        for value in df[uid_column].tolist()
        if value is not None
        for text in [str(value).strip()]
        if text
    })
    preview_rows = df.head(20).fillna("").to_dict(orient="records")
    return {
        "uids": uids,
        "rows_actual": int(len(df)),
        "rows_estimated": int(rows_estimated),
        "preview_rows": preview_rows,
    }


def _execute_bucket_writeback(*, run, sql_text: str, approved_by: str) -> dict[str, Any]:
    _normalized_country, full_country = resolve_country_names(run.country)
    request = ExecuteRequest(
        approved_sql=sql_text,
        sql_kind="query_only",
        target_country=TargetCountry(full_country),
        approved_by=approved_by,
        output_bucket=run.output_bucket,
        output_format=run.output_format,
        uid_column=run.uid_column or "uid",
        overwrite=bool(run.overwrite),
    )
    payload = run_execute_pipeline(request, request_id=uuid.uuid4().hex)
    filenames = payload.get("filenames") or []
    return {
        "rows_actual": payload.get("metadata", {}).get("row_count_total"),
        "rows_estimated": payload.get("metadata", {}).get("row_count_total"),
        "uids": list((payload.get("rows_per_uid") or {}).keys()),
        "preview_rows": [],
        "artifact": {
            "filenames": filenames,
            "written_file_count": payload.get("written_file_count"),
            "total_uids": payload.get("total_uids"),
            "rows_per_uid": payload.get("rows_per_uid") or {},
        },
        "output_bucket": payload.get("output_bucket"),
        "output_format": payload.get("output_format"),
        "target_dir": payload.get("target_dir"),
        "written_uid_count": payload.get("total_uids"),
    }


def _is_under_specified_writeback_request(
    *,
    natural_language_request: str,
    run_type: str,
    output_bucket: str | None,
) -> bool:
    if run_type != "bucket_writeback" or not output_bucket:
        return False
    request = str(natural_language_request or "").strip().lower()
    if not request:
        return True
    explicit_uid = any(token in request for token in ("uid", "uuid", "user_id", "userid", "用户id", "用户 id", "用户列表"))
    has_cohort_condition = any(
        token in request
        for token in (
            "最近",
            "首贷",
            "逾期",
            "高风险",
            "cohort",
            "从未",
            "7 天",
            "7天",
            "注册用户",
            "逾期用户",
            "first-loan",
            "never-overdue",
        )
    )
    return not explicit_uid and not has_cohort_condition


def _append_unsupported_field_warnings(
    *,
    safety_result: dict[str, Any],
    sql_text: str,
    retrieval_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    snapshot = dict(retrieval_snapshot or {})
    grounded = {
        normalize_table_name(table_name): {normalize_field_name(field) for field in field_names or [] if normalize_field_name(field)}
        for table_name, field_names in (snapshot.get("grounded_fields_by_table") or {}).items()
        if normalize_table_name(table_name)
    }
    canonical_alternative_to_preferred = {
        normalize_table_name(table_name): {
            normalize_field_name(field): normalize_field_name(preferred_field)
            for field, preferred_field in (field_mapping or {}).items()
            if normalize_field_name(field) and normalize_field_name(preferred_field)
        }
        for table_name, field_mapping in (snapshot.get("canonical_alternative_to_preferred_by_table") or {}).items()
        if normalize_table_name(table_name)
    }
    if not grounded:
        return safety_result

    sql_wo_strings = re.sub(r"'(?:''|[^'])*'", " ", str(sql_text or ""))
    cte_names = {match.group(1).lower() for match in _WITH_CTE_RE.finditer(sql_wo_strings)}
    alias_to_table: dict[str, str] = {}
    base_tables: list[str] = []
    raw_table_tokens: set[str] = set()
    has_join = False
    for match in _FROM_JOIN_RE.finditer(sql_wo_strings):
        raw_table = match.group(1)
        raw_alias = match.group(2)
        table_name = normalize_table_name(raw_table)
        raw_table_tokens.update(
            normalize_field_name(part)
            for part in raw_table.split(".")
            if normalize_field_name(part)
        )
        if table_name in cte_names:
            continue
        if match.group(0).lower().startswith("join"):
            has_join = True
        if table_name not in base_tables:
            base_tables.append(table_name)
        alias_to_table[table_name] = table_name
        if raw_alias:
            alias = raw_alias.lower()
            if alias not in _SQL_KEYWORDS:
                alias_to_table[alias] = table_name

    warnings = list(safety_result.get("warnings") or [])
    seen_pairs = {(item.get("table"), item.get("field")) for item in warnings if isinstance(item, dict)}

    def _append_non_canonical_warning(*, table_name: str, field_name: str, preferred_field: str) -> None:
        warnings.append(
            {
                "category": "NON_CANONICAL_FIELD",
                "risk_level": "low",
                "table": table_name,
                "field": field_name,
                "preferred_field": preferred_field,
                "message": f"Field {field_name} is grounded for {table_name}, but prefer {preferred_field} for this semantic unless the current request explicitly requires {field_name}.",
            }
        )

    def _append_unsupported_warning(*, table_name: str, field_name: str) -> None:
        warnings.append(
            {
                "category": "UNSUPPORTED_FIELD",
                "risk_level": "medium",
                "table": table_name,
                "field": field_name,
                "message": f"Field {field_name} is not found in retrieved catalog/glossary for {table_name}.",
            }
        )

    for alias, field in _QUALIFIED_FIELD_RE.findall(sql_wo_strings):
        alias_key = alias.lower()
        field_key = normalize_field_name(field)
        table_name = alias_to_table.get(alias_key)
        if not table_name or table_name not in grounded:
            continue
        if field_key in grounded[table_name]:
            preferred_field = canonical_alternative_to_preferred.get(table_name, {}).get(field_key)
            if preferred_field:
                pair = (table_name, field_key)
                if pair not in seen_pairs:
                    _append_non_canonical_warning(table_name=table_name, field_name=field_key, preferred_field=preferred_field)
                    seen_pairs.add(pair)
            continue
        pair = (table_name, field_key)
        if pair in seen_pairs:
            continue
        _append_unsupported_warning(table_name=table_name, field_name=field_key)
        seen_pairs.add(pair)

    if cte_names or has_join or len(base_tables) != 1:
        safety_result["warnings"] = warnings
        return safety_result

    functions = {match.group(1).lower() for match in _FUNCTION_RE.finditer(sql_wo_strings)}
    select_aliases = {match.group(1).lower() for match in _AS_ALIAS_RE.finditer(sql_wo_strings)}
    only_table = base_tables[0]
    table_tokens = set(alias_to_table.keys()) | {only_table} | raw_table_tokens
    for token in _FIELD_TOKEN_RE.findall(sql_wo_strings):
        token_key = normalize_field_name(token)
        if token_key in _SQL_KEYWORDS or token_key in functions or token_key in table_tokens or token_key in select_aliases:
            continue
        if token_key in grounded.get(only_table, set()):
            preferred_field = canonical_alternative_to_preferred.get(only_table, {}).get(token_key)
            if preferred_field:
                pair = (only_table, token_key)
                if pair not in seen_pairs:
                    _append_non_canonical_warning(table_name=only_table, field_name=token_key, preferred_field=preferred_field)
                    seen_pairs.add(pair)
            continue
        pair = (only_table, token_key)
        if pair in seen_pairs:
            continue
        _append_unsupported_warning(table_name=only_table, field_name=token_key)
        seen_pairs.add(pair)

    safety_result["warnings"] = warnings
    return safety_result


def _review_sql_candidate(
    *,
    sql_text: str,
    sql_kind: str,
    target_country: str,
    retrieval_snapshot: dict[str, Any] | None,
    natural_language_request: str,
    run_type: str,
    output_bucket: str | None,
) -> dict[str, Any]:
    safety_result = run_sql_safety_gate(sql_text, sql_kind, target_country)
    safety_result = _append_unsupported_field_warnings(
        safety_result=safety_result,
        sql_text=sql_text,
        retrieval_snapshot=retrieval_snapshot,
    )
    safety_result["warnings"] = list(safety_result.get("warnings") or []) + review_sql_against_intent_plan(
        sql_text=sql_text,
        retrieval_snapshot=retrieval_snapshot or {},
        natural_language_request=natural_language_request,
        run_type=run_type,
        output_bucket=output_bucket,
    )
    return safety_result


def _warning_categories(warnings: list[dict[str, Any]] | None) -> list[str]:
    return [str(item.get("category") or "") for item in (warnings or []) if str(item.get("category") or "")]


def _has_more_severe_plan_warning(
    *,
    original_warnings: list[dict[str, Any]],
    repaired_warnings: list[dict[str, Any]],
) -> bool:
    severe_categories = {"PLAN_BROAD_SCAN_RISK", "PLAN_REQUIRED_FIELD_MISSING", "PLAN_FORBIDDEN_PATTERN"}
    original_categories = {str(item.get("category") or "") for item in original_warnings}
    repaired_categories = {str(item.get("category") or "") for item in repaired_warnings}
    return bool((repaired_categories & severe_categories) - original_categories)


def _build_repair_trace(
    *,
    attempted: bool,
    applied: bool,
    trigger_categories: list[str],
    original_safety_result: dict[str, Any],
    final_safety_result: dict[str, Any],
    selection_reason: str | None = None,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "attempted": attempted,
        "applied": applied,
        "attempt_count": 1 if attempted else 0,
        "trigger_categories": trigger_categories,
        "original_sql_hash": original_safety_result.get("sql_hash"),
        "original_warning_categories": _warning_categories(list(original_safety_result.get("warnings") or [])),
        "final_warning_categories": _warning_categories(list(final_safety_result.get("warnings") or [])),
    }
    if selection_reason:
        payload["selection_reason"] = selection_reason
    if failure_reason:
        payload["failure_reason"] = failure_reason
    return payload


class DataAgentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = DataAgentRepository(db)

    def _fallback_after_failed_repair(
        self,
        *,
        original_safety_result: dict[str, Any],
        trigger_categories: list[str],
        original_source: str,
        failure_reason: str,
        final_safety_result: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any], str]:
        fallback = dict(original_safety_result)
        fallback["warnings"] = list(original_safety_result.get("warnings") or [])
        fallback["repair"] = _build_repair_trace(
            attempted=True,
            applied=False,
            trigger_categories=trigger_categories,
            original_safety_result=original_safety_result,
            final_safety_result=final_safety_result or original_safety_result,
            failure_reason=failure_reason,
        )
        return original_source, fallback

    def _maybe_apply_plan_guided_repair(
        self,
        *,
        request_text: str,
        reviewer_feedback: str | None,
        prompt_context,
        target_country: str,
        target_action: str,
        run_type: str,
        output_bucket: str | None,
        retrieval_snapshot: dict[str, Any] | None,
        original_sql_kind: str,
        original_safety_result: dict[str, Any],
        original_source: str,
        run_id: str | None = None,
    ) -> tuple[str, str, dict[str, Any]]:
        original_warnings = list(original_safety_result.get("warnings") or [])
        repairable_warnings = select_repairable_plan_warnings(original_warnings)
        if original_safety_result.get("status") == "blocked" or not repairable_warnings:
            return original_source, original_sql_kind, original_safety_result

        trigger_categories = [str(item.get("category") or "") for item in repairable_warnings]
        repair_instruction = build_plan_guided_repair_instruction(
            sql_text=str(original_safety_result.get("normalized_sql") or ""),
            plan_warnings=repairable_warnings,
            retrieval_snapshot=retrieval_snapshot or {},
            natural_language_request=request_text,
            run_type=run_type,
            output_bucket=output_bucket,
            reviewer_feedback=reviewer_feedback,
        )
        repair_request = f"{request_text}\n\nRepair instruction:\n{repair_instruction}"
        try:
            repaired_generated = _generate_sql_response(
                natural_language_request=repair_request,
                target_country=target_country,
                target_action=target_action,
                knowledge_prompt_context=prompt_context,
            )
        except OrchestratorError:
            original_source, original_safety_result = self._fallback_after_failed_repair(
                original_safety_result=original_safety_result,
                trigger_categories=trigger_categories,
                original_source=original_source,
                failure_reason="generation_error",
            )
            return original_source, original_sql_kind, original_safety_result

        try:
            repaired_sql_text = self._require_generated_sql(repaired_generated, run_id=run_id)
        except HTTPException:
            original_source, original_safety_result = self._fallback_after_failed_repair(
                original_safety_result=original_safety_result,
                trigger_categories=trigger_categories,
                original_source=original_source,
                failure_reason="empty_sql",
            )
            return original_source, original_sql_kind, original_safety_result

        repaired_sql_kind = str(repaired_generated.get("sql_kind") or original_sql_kind or "query_only")
        repaired_safety_result = _review_sql_candidate(
            sql_text=repaired_sql_text,
            sql_kind=repaired_sql_kind,
            target_country=target_country,
            retrieval_snapshot=retrieval_snapshot,
            natural_language_request=request_text,
            run_type=run_type,
            output_bucket=output_bucket,
        )
        repaired_warnings = list(repaired_safety_result.get("warnings") or [])
        repaired_repairable_warnings = select_repairable_plan_warnings(repaired_warnings)
        if repaired_safety_result.get("status") == "blocked" and original_safety_result.get("status") != "blocked":
            original_source, original_safety_result = self._fallback_after_failed_repair(
                original_safety_result=original_safety_result,
                trigger_categories=trigger_categories,
                original_source=original_source,
                failure_reason="safety_regression",
                final_safety_result=repaired_safety_result,
            )
            return original_source, original_sql_kind, original_safety_result
        if _has_more_severe_plan_warning(
            original_warnings=original_warnings,
            repaired_warnings=repaired_warnings,
        ):
            original_source, original_safety_result = self._fallback_after_failed_repair(
                original_safety_result=original_safety_result,
                trigger_categories=trigger_categories,
                original_source=original_source,
                failure_reason="introduced_more_severe_warning",
                final_safety_result=repaired_safety_result,
            )
            return original_source, original_sql_kind, original_safety_result
        if len(repaired_repairable_warnings) >= len(repairable_warnings):
            original_source, original_safety_result = self._fallback_after_failed_repair(
                original_safety_result=original_safety_result,
                trigger_categories=trigger_categories,
                original_source=original_source,
                failure_reason="repairable_warnings_not_reduced",
                final_safety_result=repaired_safety_result,
            )
            return original_source, original_sql_kind, original_safety_result

        selection_reason = (
            "repair_removed_trigger_warnings"
            if not repaired_repairable_warnings
            else "repair_reduced_repairable_warning_count"
        )
        repaired_safety_result["repair"] = _build_repair_trace(
            attempted=True,
            applied=True,
            trigger_categories=trigger_categories,
            original_safety_result=original_safety_result,
            final_safety_result=repaired_safety_result,
            selection_reason=selection_reason,
        )
        return original_source, repaired_sql_kind, repaired_safety_result

    @staticmethod
    def _unpack_generation_context(result):
        if isinstance(result, tuple) and len(result) == 6:
            return result
        if isinstance(result, tuple) and len(result) == 5:
            retrieved_context, deterministic_prompt_context, prompt_context, retrieval_snapshot, hybrid_audit_summary = result
            return retrieved_context, deterministic_prompt_context, prompt_context, retrieval_snapshot, retrieval_snapshot, hybrid_audit_summary
        if isinstance(result, tuple) and len(result) == 4:
            retrieved_context, prompt_context, retrieval_snapshot, hybrid_audit_summary = result
            return retrieved_context, prompt_context, prompt_context, retrieval_snapshot, retrieval_snapshot, hybrid_audit_summary
        if isinstance(result, tuple) and len(result) == 3:
            retrieved_context, prompt_context, retrieval_snapshot = result
            return retrieved_context, prompt_context, prompt_context, retrieval_snapshot, retrieval_snapshot, {}
        raise ValueError("unexpected _build_generation_context return shape")

    @staticmethod
    def _is_candidate_only_http_exception(exc: HTTPException) -> bool:
        if int(getattr(exc, "status_code", 0) or 0) != 422:
            return False
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        stage = str(detail.get("stage") or "").strip().lower()
        return stage in {"data_agent_sql_generation", "data_agent_sql_planning"}

    @staticmethod
    def _build_structured_plan_provenance(
        *,
        plan_generation_pass: str,
        prompt_injection_mode: str,
        source_context: str,
    ) -> dict[str, str]:
        return {
            "plan_generation_pass": plan_generation_pass,
            "prompt_injection_mode": prompt_injection_mode,
            "source_context": source_context,
        }

    @staticmethod
    def _build_attempt_trace(
        trace: dict[str, Any] | None,
        *,
        plan_generation_pass: str,
        prompt_injection_mode: str,
    ) -> dict[str, Any] | None:
        if trace is None:
            return None
        updated = copy.deepcopy(trace)
        configured_mode = str(updated.get("configured_mode") or "")
        effective_mode = str(updated.get("effective_mode") or "")
        if (
            configured_mode in {"hybrid_candidate", "hybrid_enabled"}
            and effective_mode in {"hybrid_candidate", "hybrid_enabled"}
            and prompt_injection_mode == PROMPT_INJECTION_NONE
        ):
            updated["effective_mode"] = "deterministic_only"
            updated["prompt_injection_mode"] = PROMPT_INJECTION_NONE
            updated["prompt_candidate_count"] = 0
        updated["final_generation_pass"] = plan_generation_pass
        return updated

    def _build_attempt_generation_artifacts(
        self,
        *,
        natural_language_request: str,
        target_country: str,
        run_type: str,
        output_bucket: str | None,
        run_id: str | None,
        project_id: int | None,
        retrieved_context,
        base_snapshot: dict[str, Any],
        hybrid_trace: dict[str, Any] | None,
        prompt_injection_mode: str,
        plan_generation_pass: str,
        source_context: str,
        supplemental_prompt_section: str = "",
    ):
        assembler = PromptContextAssembler()
        provenance = self._build_structured_plan_provenance(
            plan_generation_pass=plan_generation_pass,
            prompt_injection_mode=prompt_injection_mode,
            source_context=source_context,
        )
        planning_snapshot = dict(base_snapshot)
        planning_snapshot[_STRUCTURED_SQL_PLAN_PROVENANCE_KEY] = provenance
        if hybrid_trace is not None:
            planning_snapshot["hybrid_trace"] = copy.deepcopy(hybrid_trace)
        structured_plan = build_structured_sql_plan(
            natural_language_request=natural_language_request,
            run_type=run_type,
            output_bucket=output_bucket,
            country=target_country,
            retrieval_snapshot=planning_snapshot,
        )
        validation = validate_structured_sql_plan(
            plan=structured_plan,
            retrieval_snapshot=planning_snapshot,
        )
        if not validation.valid:
            self._raise_plan_validation_http_error(validation_result=validation, run_id=run_id)
        structured_plan_payload = structured_plan.model_dump(mode="json")
        structured_validation_payload = validation.model_dump(mode="json")
        prompt_context = assembler.assemble(
            natural_language_request=natural_language_request,
            country=target_country,
            run_type=run_type,
            output_bucket=output_bucket,
            context=retrieved_context,
            structured_plan=structured_plan_payload,
        )
        if prompt_injection_mode == PROMPT_INJECTION_SUPPLEMENTAL_CANDIDATES_V1 and supplemental_prompt_section:
            prompt_context = append_prompt_section(prompt_context, supplemental_prompt_section)
        snapshot = assembler.build_snapshot(
            country=target_country,
            project_id=project_id,
            natural_language_request=natural_language_request,
            run_type=run_type,
            output_bucket=output_bucket,
            context=retrieved_context,
            assembled=prompt_context,
            structured_plan=structured_plan_payload,
            structured_plan_validation=structured_validation_payload,
        )
        snapshot[_STRUCTURED_SQL_PLAN_PROVENANCE_KEY] = provenance
        if hybrid_trace is not None:
            snapshot["hybrid_trace"] = copy.deepcopy(hybrid_trace)
        hybrid_audit_summary = extract_hybrid_audit_summary({"hybrid_trace": snapshot.get("hybrid_trace")})
        return prompt_context, snapshot, hybrid_audit_summary

    @staticmethod
    def _active_hybrid_attempt_mode(*, prompt_context, retrieval_snapshot: dict[str, Any]) -> str | None:
        trace = dict((retrieval_snapshot or {}).get("hybrid_trace") or {})
        attempted_mode = str((trace.get("candidate_attempt") or {}).get("attempted_mode") or "")
        if attempted_mode not in {"hybrid_candidate", "hybrid_enabled"}:
            attempted_mode = str(trace.get("effective_mode") or "")
        if attempted_mode not in {"hybrid_candidate", "hybrid_enabled"}:
            return None
        if not (
            str(trace.get("effective_mode") or "") == attempted_mode
            and str(trace.get("prompt_injection_mode") or "") == PROMPT_INJECTION_SUPPLEMENTAL_CANDIDATES_V1
            and bool(getattr(prompt_context, "rendered_text", ""))
            and "Supplemental Hybrid Knowledge Candidates" in str(getattr(prompt_context, "rendered_text", ""))
        ):
            return None
        return attempted_mode

    @staticmethod
    def _candidate_sql_hash(sql_text: str | None) -> str | None:
        normalized = str(sql_text or "").strip()
        if not normalized:
            return None
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _mark_candidate_attempt(
        trace: dict[str, Any] | None,
        *,
        attempted_mode: str | None = None,
        sql_kind: str | None = None,
        sql_text: str | None = None,
        discarded: bool = False,
        discard_reason: str | None = None,
        final_effective_mode: str | None = None,
        final_prompt_injection_mode: str | None = None,
        final_prompt_candidate_count: int | None = None,
        final_generation_pass: str | None = None,
        fallback_reason: str | None = None,
        fallback_applied: bool | None = None,
    ) -> dict[str, Any] | None:
        if not trace:
            return None
        updated = dict(trace)
        attempt = dict(updated.get("candidate_attempt") or {})
        attempt["attempted"] = True
        if attempted_mode is not None:
            attempt["attempted_mode"] = attempted_mode
        elif attempt.get("attempted_mode") is None:
            attempt["attempted_mode"] = "hybrid_candidate"
        if sql_kind is not None:
            attempt["output_sql_kind"] = str(sql_kind or "").strip().lower() or None
        if sql_text is not None:
            attempt["output_sql_hash"] = DataAgentService._candidate_sql_hash(sql_text)
        attempt["discarded"] = bool(discarded)
        attempt["discard_reason"] = discard_reason
        updated["candidate_attempt"] = attempt
        if final_effective_mode is not None:
            updated["effective_mode"] = final_effective_mode
        if final_prompt_injection_mode is not None:
            updated["prompt_injection_mode"] = final_prompt_injection_mode
        if final_prompt_candidate_count is not None:
            updated["prompt_candidate_count"] = final_prompt_candidate_count
        if final_generation_pass is not None:
            updated["final_generation_pass"] = final_generation_pass
        if fallback_reason is not None:
            updated["fallback_reason"] = fallback_reason
        if fallback_applied is not None:
            updated["fallback_applied"] = fallback_applied
        return updated

    def _generate_sql_with_hybrid_fallback(
        self,
        *,
        natural_language_request: str,
        target_country: str,
        target_action: str,
        candidate_prompt_context,
        deterministic_prompt_context,
        deterministic_retrieval_snapshot: dict[str, Any],
        retrieval_snapshot: dict[str, Any],
        hybrid_audit_summary: dict[str, Any],
        run_id: str | None = None,
    ):
        attempt_mode = self._active_hybrid_attempt_mode(
            prompt_context=candidate_prompt_context,
            retrieval_snapshot=retrieval_snapshot,
        )
        if attempt_mode is None:
            generated = _generate_sql_response(
                natural_language_request=natural_language_request,
                target_country=target_country,
                target_action=target_action,
                knowledge_prompt_context=candidate_prompt_context,
            )
            return generated, candidate_prompt_context, retrieval_snapshot, hybrid_audit_summary

        try:
            generated = _generate_sql_response(
                natural_language_request=natural_language_request,
                target_country=target_country,
                target_action=target_action,
                knowledge_prompt_context=candidate_prompt_context,
            )
        except OrchestratorError:
            deterministic_snapshot = copy.deepcopy(deterministic_retrieval_snapshot)
            deterministic_snapshot["hybrid_trace"] = self._mark_candidate_attempt(
                deterministic_snapshot.get("hybrid_trace"),
                attempted_mode=attempt_mode,
                discarded=True,
                discard_reason=DISCARD_REASON_CANDIDATE_GENERATION_FAILED,
                final_effective_mode="deterministic_only",
                final_prompt_injection_mode=PROMPT_INJECTION_NONE,
                final_prompt_candidate_count=0,
                final_generation_pass=FINAL_GENERATION_PASS_DETERMINISTIC_RERUN,
                fallback_reason=DISCARD_REASON_CANDIDATE_GENERATION_FAILED,
                fallback_applied=True,
            )
            deterministic_snapshot[_STRUCTURED_SQL_PLAN_PROVENANCE_KEY] = self._build_structured_plan_provenance(
                plan_generation_pass=FINAL_GENERATION_PASS_DETERMINISTIC_RERUN,
                prompt_injection_mode=PROMPT_INJECTION_NONE,
                source_context=_SOURCE_CONTEXT_DETERMINISTIC_RERUN_ATTEMPT,
            )
            hybrid_audit_summary = extract_hybrid_audit_summary({"hybrid_trace": deterministic_snapshot.get("hybrid_trace")})
            rerun_generated = _generate_sql_response(
                natural_language_request=natural_language_request,
                target_country=target_country,
                target_action=target_action,
                knowledge_prompt_context=deterministic_prompt_context,
            )
            return rerun_generated, deterministic_prompt_context, deterministic_snapshot, hybrid_audit_summary

        try:
            candidate_sql_text = self._require_generated_sql(generated, run_id=run_id)
        except HTTPException as exc:
            if not self._is_candidate_only_http_exception(exc):
                raise
            deterministic_snapshot = copy.deepcopy(deterministic_retrieval_snapshot)
            deterministic_snapshot["hybrid_trace"] = self._mark_candidate_attempt(
                deterministic_snapshot.get("hybrid_trace"),
                attempted_mode=attempt_mode,
                discarded=True,
                discard_reason=DISCARD_REASON_CANDIDATE_SQL_EMPTY,
                final_effective_mode="deterministic_only",
                final_prompt_injection_mode=PROMPT_INJECTION_NONE,
                final_prompt_candidate_count=0,
                final_generation_pass=FINAL_GENERATION_PASS_DETERMINISTIC_RERUN,
                fallback_reason=DISCARD_REASON_CANDIDATE_GENERATION_FAILED,
                fallback_applied=True,
            )
            deterministic_snapshot[_STRUCTURED_SQL_PLAN_PROVENANCE_KEY] = self._build_structured_plan_provenance(
                plan_generation_pass=FINAL_GENERATION_PASS_DETERMINISTIC_RERUN,
                prompt_injection_mode=PROMPT_INJECTION_NONE,
                source_context=_SOURCE_CONTEXT_DETERMINISTIC_RERUN_ATTEMPT,
            )
            hybrid_audit_summary = extract_hybrid_audit_summary({"hybrid_trace": deterministic_snapshot.get("hybrid_trace")})
            rerun_generated = _generate_sql_response(
                natural_language_request=natural_language_request,
                target_country=target_country,
                target_action=target_action,
                knowledge_prompt_context=deterministic_prompt_context,
            )
            return rerun_generated, deterministic_prompt_context, deterministic_snapshot, hybrid_audit_summary
        candidate_sql_kind = str(generated.get("sql_kind") or "query_only")
        if str(candidate_sql_kind).strip().lower() == "query_only":
            final_generation_pass = (
                FINAL_GENERATION_PASS_HYBRID_ENABLED
                if attempt_mode == "hybrid_enabled"
                else FINAL_GENERATION_PASS_HYBRID_CANDIDATE
            )
            source_context = (
                _SOURCE_CONTEXT_HYBRID_ENABLED_ATTEMPT
                if attempt_mode == "hybrid_enabled"
                else _SOURCE_CONTEXT_HYBRID_CANDIDATE_ATTEMPT
            )
            retrieval_snapshot["hybrid_trace"] = self._mark_candidate_attempt(
                retrieval_snapshot.get("hybrid_trace"),
                attempted_mode=attempt_mode,
                sql_kind=candidate_sql_kind,
                sql_text=candidate_sql_text,
                discarded=False,
                discard_reason=None,
                final_effective_mode=attempt_mode,
                final_prompt_injection_mode=PROMPT_INJECTION_SUPPLEMENTAL_CANDIDATES_V1,
                final_prompt_candidate_count=int((retrieval_snapshot.get("hybrid_trace") or {}).get("prompt_candidate_count") or 0),
                final_generation_pass=final_generation_pass,
                fallback_reason=None,
                fallback_applied=False,
            )
            retrieval_snapshot[_STRUCTURED_SQL_PLAN_PROVENANCE_KEY] = self._build_structured_plan_provenance(
                plan_generation_pass=final_generation_pass,
                prompt_injection_mode=PROMPT_INJECTION_SUPPLEMENTAL_CANDIDATES_V1,
                source_context=source_context,
            )
            hybrid_audit_summary = extract_hybrid_audit_summary(retrieval_snapshot)
            return generated, candidate_prompt_context, retrieval_snapshot, hybrid_audit_summary

        deterministic_snapshot = copy.deepcopy(deterministic_retrieval_snapshot)
        deterministic_snapshot["hybrid_trace"] = self._mark_candidate_attempt(
            deterministic_snapshot.get("hybrid_trace"),
            attempted_mode=attempt_mode,
            sql_kind=candidate_sql_kind,
            sql_text=candidate_sql_text,
            discarded=True,
            discard_reason=DISCARD_REASON_POST_SQL_KIND_MISMATCH,
            final_effective_mode="deterministic_only",
            final_prompt_injection_mode=PROMPT_INJECTION_NONE,
            final_prompt_candidate_count=0,
            final_generation_pass=FINAL_GENERATION_PASS_DETERMINISTIC_RERUN,
            fallback_reason="unsupported_sql_kind",
            fallback_applied=True,
        )
        deterministic_snapshot[_STRUCTURED_SQL_PLAN_PROVENANCE_KEY] = self._build_structured_plan_provenance(
            plan_generation_pass=FINAL_GENERATION_PASS_DETERMINISTIC_RERUN,
            prompt_injection_mode=PROMPT_INJECTION_NONE,
            source_context=_SOURCE_CONTEXT_DETERMINISTIC_RERUN_ATTEMPT,
        )
        hybrid_audit_summary = extract_hybrid_audit_summary({"hybrid_trace": deterministic_snapshot.get("hybrid_trace")})
        rerun_generated = _generate_sql_response(
            natural_language_request=natural_language_request,
            target_country=target_country,
            target_action=target_action,
            knowledge_prompt_context=deterministic_prompt_context,
        )
        return rerun_generated, deterministic_prompt_context, deterministic_snapshot, hybrid_audit_summary

    def create_run(self, *, ctx: UserContext, body: DataAgentRunCreateRequest) -> DataAgentRunDetail:
        require_permissions(ctx, ("data:query:generate", "data:query:view_sql"))
        target_country = normalize_country_scope_value(body.target_country) or body.target_country.lower()
        require_country_access(ctx, target_country, project_id=ctx.project_id)
        _retrieved_context, deterministic_prompt_context, prompt_context, deterministic_retrieval_snapshot, retrieval_snapshot, hybrid_audit_summary = self._unpack_generation_context(
            self._build_generation_context(
                natural_language_request=body.natural_language_request,
                target_country=target_country,
                run_type=body.run_type,
                output_bucket=body.output_bucket,
                ctx=ctx,
                run_id=None,
            )
        )

        try:
            generated, prompt_context, retrieval_snapshot, hybrid_audit_summary = self._generate_sql_with_hybrid_fallback(
                natural_language_request=body.natural_language_request,
                target_country=target_country,
                target_action=body.target_action,
                candidate_prompt_context=prompt_context,
                deterministic_prompt_context=deterministic_prompt_context,
                deterministic_retrieval_snapshot=deterministic_retrieval_snapshot,
                retrieval_snapshot=retrieval_snapshot,
                hybrid_audit_summary=hybrid_audit_summary,
            )
        except OrchestratorError as exc:
            self._raise_generation_http_error(
                exc,
                natural_language_request=body.natural_language_request,
                run_type=body.run_type,
                output_bucket=body.output_bucket,
            )
        sql_text = self._require_generated_sql(generated)
        sql_kind = str(generated.get("sql_kind") or "query_only")
        safety_result = _review_sql_candidate(
            sql_text=sql_text,
            sql_kind=sql_kind,
            target_country=target_country,
            retrieval_snapshot=retrieval_snapshot,
            natural_language_request=body.natural_language_request,
            run_type=body.run_type,
            output_bucket=body.output_bucket,
        )
        source, sql_kind, safety_result = self._maybe_apply_plan_guided_repair(
            request_text=body.natural_language_request,
            reviewer_feedback=None,
            prompt_context=prompt_context,
            target_country=target_country,
            target_action=body.target_action,
            run_type=body.run_type,
            output_bucket=body.output_bucket,
            retrieval_snapshot=retrieval_snapshot,
            original_sql_kind=sql_kind,
            original_safety_result=safety_result,
            original_source="agent_generated",
        )
        finalized_hybrid_trace = finalize_shadow_trace_for_sql_kind(
            retrieval_snapshot.get("hybrid_trace"),
            sql_kind=sql_kind,
        )
        if finalized_hybrid_trace is not None:
            retrieval_snapshot["hybrid_trace"] = finalized_hybrid_trace
            hybrid_audit_summary = extract_hybrid_audit_summary(retrieval_snapshot)
        run_id = uuid.uuid4().hex
        run = self.repo.create_run(
            run_id=run_id,
            user_id=int(ctx.user_id) if str(ctx.user_id).isdigit() else None,
            project_id=int(ctx.project_id) if ctx.project_id and str(ctx.project_id).isdigit() else None,
            country=target_country,
            run_type=body.run_type,
            natural_language_request=body.natural_language_request,
            status="awaiting_review",
            sql_kind=sql_kind,
            output_bucket=body.output_bucket,
            output_format=body.output_format,
            uid_column=body.uid_column,
            overwrite=body.overwrite,
        )
        version = self.repo.add_sql_version(
            run_id=run_id,
            version_no=1,
            sql_text=safety_result["normalized_sql"],
            sql_hash=safety_result["sql_hash"],
            source=source,
            sql_kind=sql_kind,
            safety_status=safety_result["status"],
            safety_result_json=safety_result,
            retrieval_snapshot_json=retrieval_snapshot,
            created_by=ctx.username,
        )
        run.current_sql_version_id = version.id
        run.updated_at = datetime.utcnow()
        self.db.commit()

        self._audit(
            ctx=ctx,
            event_type="data.query.run_created",
            action="create",
            run=run,
            sql_hash=version.sql_hash,
            extra_metadata=hybrid_audit_summary,
        )
        self._audit(
            ctx=ctx,
            event_type="data.query.sql_generated",
            action="generate",
            run=run,
            sql_hash=version.sql_hash,
            extra_metadata=hybrid_audit_summary,
        )
        return self.get_run_detail(ctx=ctx, run_id=run_id)

    def list_runs(self, *, ctx: UserContext) -> DataAgentRunListResponse:
        runs = self.repo.list_runs(
            project_id=int(ctx.project_id) if ctx.project_id and str(ctx.project_id).isdigit() else None,
            country=normalize_country_scope_value(ctx.country) if ctx.country else None,
        )
        can_view_sql = "data:query:view_sql" in ctx.permissions
        return DataAgentRunListResponse(runs=[self._to_summary(run, can_view_sql=can_view_sql) for run in runs])

    def get_run_detail(self, *, ctx: UserContext, run_id: str) -> DataAgentRunDetail:
        run = self._get_scoped_run(ctx, run_id)
        return self._to_detail(run, can_view_sql="data:query:view_sql" in ctx.permissions)

    def approve_run(self, *, ctx: UserContext, run_id: str, comment: str | None = None) -> DataAgentRunDetail:
        require_permissions(ctx, ("data:query:review", "data:query:view_sql"))
        run = self._get_scoped_run(ctx, run_id)
        current = self.repo.get_sql_version(run.current_sql_version_id)
        if current is None:
            raise HTTPException(status_code=409, detail="run has no current SQL version")
        if current.sql_kind != "query_only" or current.safety_status != "passed":
            raise HTTPException(status_code=409, detail="current SQL is not eligible for execution approval")
        previous_hash = run.approved_sql_hash
        run.approved_sql_version_id = current.id
        run.approved_sql_hash = current.sql_hash
        run.status = "approved"
        run.updated_at = datetime.utcnow()
        self.repo.add_review_event(
            run_id=run.run_id,
            decision="approve",
            reviewer_user_id=int(ctx.user_id) if str(ctx.user_id).isdigit() else None,
            reviewer_username=ctx.username,
            comment=comment,
            from_sql_hash=previous_hash,
            to_sql_hash=current.sql_hash,
        )
        self.db.commit()
        self._audit(ctx=ctx, event_type="data.query.approved", action="approve", run=run, sql_hash=current.sql_hash)
        return self._to_detail(run, can_view_sql="data:query:view_sql" in ctx.permissions)

    def edit_run(self, *, ctx: UserContext, run_id: str, body: DataAgentEditRequest) -> DataAgentRunDetail:
        require_permissions(ctx, ("data:query:review", "data:query:view_sql"))
        run = self._get_scoped_run(ctx, run_id)
        current = self.repo.get_sql_version(run.current_sql_version_id)
        previous_hash = run.approved_sql_hash
        safety_result = run_sql_safety_gate(body.sql_text, run.sql_kind or "query_only", run.country)
        version = self.repo.add_sql_version(
            run_id=run.run_id,
            version_no=self.repo.next_version_no(run.run_id),
            sql_text=safety_result["normalized_sql"],
            sql_hash=safety_result["sql_hash"],
            source="manual_edited",
            sql_kind=run.sql_kind or "query_only",
            safety_status=safety_result["status"],
            safety_result_json=safety_result,
            created_by=ctx.username,
        )
        run.current_sql_version_id = version.id
        run.approved_sql_version_id = None
        run.approved_sql_hash = None
        run.status = "awaiting_review"
        run.updated_at = datetime.utcnow()
        self.repo.add_review_event(
            run_id=run.run_id,
            decision="edit",
            reviewer_user_id=int(ctx.user_id) if str(ctx.user_id).isdigit() else None,
            reviewer_username=ctx.username,
            comment=body.comment,
            from_sql_hash=(current.sql_hash if current is not None else previous_hash),
            to_sql_hash=version.sql_hash,
        )
        self.db.commit()
        self._audit(ctx=ctx, event_type="data.query.sql_edited", action="edit", run=run, sql_hash=version.sql_hash)
        return self._to_detail(run, can_view_sql="data:query:view_sql" in ctx.permissions)

    def revise_run(self, *, ctx: UserContext, run_id: str, body: DataAgentReviseRequest) -> DataAgentRunDetail:
        require_permissions(ctx, ("data:query:generate", "data:query:view_sql"))
        run = self._get_scoped_run(ctx, run_id)
        current = self.repo.get_sql_version(run.current_sql_version_id)
        revised_request = run.natural_language_request if not body.comment else f"{run.natural_language_request}\n\nReviewer feedback:\n{body.comment}"
        _retrieved_context, deterministic_prompt_context, prompt_context, deterministic_retrieval_snapshot, retrieval_snapshot, hybrid_audit_summary = self._unpack_generation_context(
            self._build_generation_context(
                natural_language_request=revised_request,
                target_country=run.country,
                run_type=run.run_type,
                output_bucket=run.output_bucket,
                ctx=ctx,
                run_id=run.run_id,
            )
        )
        try:
            generated, prompt_context, retrieval_snapshot, hybrid_audit_summary = self._generate_sql_with_hybrid_fallback(
                natural_language_request=revised_request,
                target_country=run.country,
                target_action="extract",
                candidate_prompt_context=prompt_context,
                deterministic_prompt_context=deterministic_prompt_context,
                deterministic_retrieval_snapshot=deterministic_retrieval_snapshot,
                retrieval_snapshot=retrieval_snapshot,
                hybrid_audit_summary=hybrid_audit_summary,
                run_id=run.run_id,
            )
        except OrchestratorError as exc:
            self._raise_generation_http_error(
                exc,
                run_id=run.run_id,
                natural_language_request=revised_request,
                run_type=run.run_type,
                output_bucket=run.output_bucket,
            )
        sql_text = self._require_generated_sql(generated, run_id=run.run_id)
        sql_kind = str(generated.get("sql_kind") or run.sql_kind or "query_only")
        safety_result = _review_sql_candidate(
            sql_text=sql_text,
            sql_kind=sql_kind,
            target_country=run.country,
            retrieval_snapshot=retrieval_snapshot,
            natural_language_request=revised_request,
            run_type=run.run_type,
            output_bucket=run.output_bucket,
        )
        source, sql_kind, safety_result = self._maybe_apply_plan_guided_repair(
            request_text=revised_request,
            reviewer_feedback=body.comment,
            prompt_context=prompt_context,
            target_country=run.country,
            target_action="extract",
            run_type=run.run_type,
            output_bucket=run.output_bucket,
            retrieval_snapshot=retrieval_snapshot,
            original_sql_kind=sql_kind,
            original_safety_result=safety_result,
            original_source="agent_revised",
            run_id=run.run_id,
        )
        finalized_hybrid_trace = finalize_shadow_trace_for_sql_kind(
            retrieval_snapshot.get("hybrid_trace"),
            sql_kind=sql_kind,
        )
        if finalized_hybrid_trace is not None:
            retrieval_snapshot["hybrid_trace"] = finalized_hybrid_trace
            hybrid_audit_summary = extract_hybrid_audit_summary(retrieval_snapshot)
        version = self.repo.add_sql_version(
            run_id=run.run_id,
            version_no=self.repo.next_version_no(run.run_id),
            sql_text=safety_result["normalized_sql"],
            sql_hash=safety_result["sql_hash"],
            source=source,
            sql_kind=sql_kind,
            safety_status=safety_result["status"],
            safety_result_json=safety_result,
            retrieval_snapshot_json=retrieval_snapshot,
            created_by=ctx.username,
        )
        run.current_sql_version_id = version.id
        run.approved_sql_version_id = None
        run.approved_sql_hash = None
        run.status = "awaiting_review"
        run.sql_kind = sql_kind
        run.updated_at = datetime.utcnow()
        self.repo.add_review_event(
            run_id=run.run_id,
            decision="revise",
            reviewer_user_id=int(ctx.user_id) if str(ctx.user_id).isdigit() else None,
            reviewer_username=ctx.username,
            comment=body.comment,
            from_sql_hash=(current.sql_hash if current is not None else None),
            to_sql_hash=version.sql_hash,
        )
        self._resolve_latest_open_error_case(run=run, current=version, comment=body.comment, ctx=ctx)
        self.db.commit()
        self._audit(
            ctx=ctx,
            event_type="data.query.sql_revised",
            action="revise",
            run=run,
            sql_hash=version.sql_hash,
            extra_metadata=hybrid_audit_summary,
        )
        return self._to_detail(run, can_view_sql="data:query:view_sql" in ctx.permissions)

    def reject_run(self, *, ctx: UserContext, run_id: str, comment: str | None = None) -> DataAgentRunDetail:
        require_permissions(ctx, ("data:query:review",))
        run = self._get_scoped_run(ctx, run_id)
        current = self.repo.get_sql_version(run.current_sql_version_id)
        run.status = "rejected"
        run.updated_at = datetime.utcnow()
        self.repo.add_review_event(
            run_id=run.run_id,
            decision="reject",
            reviewer_user_id=int(ctx.user_id) if str(ctx.user_id).isdigit() else None,
            reviewer_username=ctx.username,
            comment=comment,
            from_sql_hash=(current.sql_hash if current is not None else None),
            to_sql_hash=None,
        )
        self.db.commit()
        self._audit(ctx=ctx, event_type="data.query.rejected", action="reject", run=run, sql_hash=(current.sql_hash if current else None))
        return self._to_detail(run, can_view_sql="data:query:view_sql" in ctx.permissions)

    def execute_run(self, *, ctx: UserContext, run_id: str) -> DataAgentRunDetail:
        run = self._get_scoped_run(ctx, run_id)
        require_permissions(ctx, ("data:query:execute",))
        if run.run_type == "bucket_writeback":
            require_permissions(ctx, ("data:bucket:writeback",))
        current = self.repo.get_sql_version(run.current_sql_version_id)
        if current is None or run.approved_sql_version_id is None or not run.approved_sql_hash:
            raise HTTPException(status_code=409, detail="run has no approved SQL")
        if current.id != run.approved_sql_version_id or current.sql_hash != run.approved_sql_hash:
            raise HTTPException(status_code=409, detail="approved SQL hash no longer matches current SQL")
        if current.sql_kind != "query_only":
            raise HTTPException(status_code=409, detail="Only query_only SQL can be executed in M1")
        if current.safety_status != "passed":
            raise HTTPException(status_code=409, detail="current SQL safety status does not allow execution")

        run.status = "executing"
        run.updated_at = datetime.utcnow()
        self.db.commit()

        try:
            if run.run_type == "cohort_query":
                payload = _execute_cohort_query(sql_text=current.sql_text, target_country=run.country)
                self.repo.add_execution_event(
                    run_id=run.run_id,
                    run_type=run.run_type,
                    approved_sql_hash=run.approved_sql_hash,
                    executor_user_id=int(ctx.user_id) if str(ctx.user_id).isdigit() else None,
                    executor_username=ctx.username,
                    status="executed",
                    rows_estimated=payload.get("rows_estimated"),
                    rows_actual=payload.get("rows_actual"),
                    result_preview_json={
                        "uids": payload.get("uids") or [],
                        "preview_rows": payload.get("preview_rows") or [],
                    },
                )
                run.status = "executed"
                run.updated_at = datetime.utcnow()
                self._persist_sql_example(run=run, current=current, ctx=ctx)
                self.db.commit()
                self._audit(ctx=ctx, event_type="data.query.executed", action="execute", run=run, sql_hash=current.sql_hash)
            else:
                payload = _execute_bucket_writeback(run=run, sql_text=current.sql_text, approved_by=ctx.username)
                self.repo.add_execution_event(
                    run_id=run.run_id,
                    run_type=run.run_type,
                    approved_sql_hash=run.approved_sql_hash,
                    executor_user_id=int(ctx.user_id) if str(ctx.user_id).isdigit() else None,
                    executor_username=ctx.username,
                    status="executed",
                    rows_estimated=payload.get("rows_estimated"),
                    rows_actual=payload.get("rows_actual"),
                    result_preview_json={"uids": payload.get("uids") or []},
                )
                self.repo.add_writeback_event(
                    run_id=run.run_id,
                    approved_sql_hash=run.approved_sql_hash,
                    executor_user_id=int(ctx.user_id) if str(ctx.user_id).isdigit() else None,
                    executor_username=ctx.username,
                    output_bucket=payload.get("output_bucket") or str(run.output_bucket),
                    output_format=payload.get("output_format") or str(run.output_format),
                    target_dir=payload.get("target_dir"),
                    written_uid_count=payload.get("written_uid_count"),
                    artifact_json=payload.get("artifact"),
                    status="executed",
                )
                run.status = "executed"
                run.updated_at = datetime.utcnow()
                self._persist_sql_example(run=run, current=current, ctx=ctx)
                self.db.commit()
                self._audit(
                    ctx=ctx,
                    event_type="data.query.executed",
                    action="execute",
                    run=run,
                    sql_hash=current.sql_hash,
                    extra_metadata={"target_dir": payload.get("target_dir")},
                )
                self._audit(
                    ctx=ctx,
                    event_type="data.bucket.writeback",
                    action="writeback",
                    run=run,
                    sql_hash=current.sql_hash,
                    extra_metadata={"target_dir": payload.get("target_dir")},
                )
        except HTTPException:
            run.status = "failed"
            run.updated_at = datetime.utcnow()
            self._open_error_case(run=run, current=current, ctx=ctx, error_message="execute_http_error")
            self.db.commit()
            self._audit(ctx=ctx, event_type="data.query.failed", action="execute", run=run, sql_hash=current.sql_hash, status="error")
            raise
        except Exception as exc:
            self.repo.add_execution_event(
                run_id=run.run_id,
                run_type=run.run_type,
                approved_sql_hash=run.approved_sql_hash,
                executor_user_id=int(ctx.user_id) if str(ctx.user_id).isdigit() else None,
                executor_username=ctx.username,
                status="failed",
                rows_estimated=None,
                rows_actual=None,
                result_preview_json=None,
                error_message=str(exc),
            )
            run.status = "failed"
            run.updated_at = datetime.utcnow()
            self._open_error_case(run=run, current=current, ctx=ctx, error_message=str(exc))
            self.db.commit()
            self._audit(ctx=ctx, event_type="data.query.failed", action="execute", run=run, sql_hash=current.sql_hash, status="error")
            raise

        return self._to_detail(run, can_view_sql="data:query:view_sql" in ctx.permissions)

    def _get_scoped_run(self, ctx: UserContext, run_id: str):
        run = self.repo.get_scoped_run(
            run_id,
            project_id=int(ctx.project_id) if ctx.project_id and str(ctx.project_id).isdigit() else None,
            country=normalize_country_scope_value(ctx.country) if ctx.country else None,
        )
        if run is None:
            raise HTTPException(status_code=404, detail="data agent run not found")
        return run

    @staticmethod
    def _raise_generation_http_error(
        exc: OrchestratorError,
        *,
        run_id: str | None = None,
        natural_language_request: str = "",
        run_type: str = "",
        output_bucket: str | None = None,
    ) -> None:
        if exc.error_type == DataAcquisitionErrorType.SCHEMA_VALIDATION_FAILED:
            if _is_under_specified_writeback_request(
                natural_language_request=natural_language_request,
                run_type=run_type,
                output_bucket=output_bucket,
            ):
                detail = {
                    "code": "DATA_AGENT_WRITEBACK_REQUIRES_COHORT",
                    "stage": "data_agent_sql_generation",
                    "reason": "Writeback requests require an explicit uid list or cohort conditions before SQL generation.",
                    "request_id": exc.request_id,
                    "retriable": True,
                }
                if run_id is not None:
                    detail["run_id"] = run_id
                raise HTTPException(status_code=422, detail=detail) from exc
            detail = {
                "code": "SCHEMA_VALIDATION_FAILED",
                "stage": "structured_output",
                "reason": "model output failed schema validation",
                "request_id": exc.request_id,
                "parse_failure_type": "schema_validation_failed",
            }
            if run_id is not None:
                detail["run_id"] = run_id
            raise HTTPException(status_code=422, detail=detail) from exc

        status_code = 422 if exc.error_type in {
            DataAcquisitionErrorType.CREDENTIAL_LEAK,
            DataAcquisitionErrorType.DANGEROUS_CODE,
            DataAcquisitionErrorType.DDL_POLICY_VIOLATION,
        } else 400
        if exc.error_type == DataAcquisitionErrorType.UPSTREAM_LLM_ERROR:
            status_code = 502
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": str(getattr(exc.error_type, "value", exc.error_type)).upper(),
                "stage": "generation",
                "reason": exc.message,
                "request_id": exc.request_id,
            },
        ) from exc

    @staticmethod
    def _require_generated_sql(generated: dict[str, Any], *, run_id: str | None = None) -> str:
        sql = generated.get("sql")
        if isinstance(sql, str):
            normalized = sql.strip()
            if normalized:
                return normalized
        detail = {
            "code": "SQL_GENERATION_REQUIRED",
            "stage": "data_agent_sql_generation",
            "reason": "Data Agent generation must produce non-empty SQL before entering SQL HITL.",
            "retriable": True,
        }
        if run_id is not None:
            detail["run_id"] = run_id
        raise HTTPException(status_code=422, detail=detail)

    @staticmethod
    def _raise_plan_validation_http_error(
        *,
        validation_result,
        run_id: str | None = None,
    ) -> None:
        detail = {
            "code": validation_result.code or "DATA_AGENT_SQL_PLAN_INVALID",
            "stage": "data_agent_sql_planning",
            "reason": validation_result.reason or "Structured SQL plan validation failed.",
            "retriable": True,
        }
        if validation_result.missing:
            detail["missing"] = list(validation_result.missing)
        if run_id is not None:
            detail["run_id"] = run_id
        raise HTTPException(status_code=422, detail=detail)

    def _to_summary(self, run, *, can_view_sql: bool) -> DataAgentRunSummary:
        current = self.repo.get_sql_version(run.current_sql_version_id)
        return DataAgentRunSummary(
            run_id=run.run_id,
            natural_language_request=run.natural_language_request,
            target_country=run.country,
            run_type=run.run_type,
            status=run.status,
            sql_kind=run.sql_kind,
            approved_sql_hash=run.approved_sql_hash,
            current_sql=(self._serialize_sql_version(current, can_view_sql=can_view_sql) if current else None),
            created_at=run.created_at.isoformat(),
            updated_at=run.updated_at.isoformat(),
        )

    def _to_detail(self, run, *, can_view_sql: bool) -> DataAgentRunDetail:
        current = self.repo.get_sql_version(run.current_sql_version_id)
        execution = self.repo.latest_execution_event(run.run_id)
        writeback = self.repo.latest_writeback_event(run.run_id)
        return DataAgentRunDetail(
            run_id=run.run_id,
            natural_language_request=run.natural_language_request,
            target_country=run.country,
            run_type=run.run_type,
            status=run.status,
            sql_kind=run.sql_kind,
            approved_sql_hash=run.approved_sql_hash,
            output_bucket=run.output_bucket,
            output_format=run.output_format,
            current_sql=(self._serialize_sql_version(current, can_view_sql=can_view_sql) if current else None),
            review_events=[self._serialize_review_event(event) for event in self.repo.list_review_events(run.run_id)],
            execution=(self._serialize_execution(execution) if execution else None),
            writeback=(self._serialize_writeback(writeback) if writeback else None),
            created_at=run.created_at.isoformat(),
            updated_at=run.updated_at.isoformat(),
        )

    def _serialize_sql_version(self, version, *, can_view_sql: bool) -> SQLVersionView:
        return SQLVersionView(
            version_id=version.id,
            version_no=version.version_no,
            sql_text=version.sql_text if can_view_sql else None,
            sql_hash=version.sql_hash,
            source=version.source,
            sql_kind=version.sql_kind,
            safety_status=version.safety_status,
            safety_result=version.safety_result_json,
            created_by=version.created_by,
            created_at=version.created_at.isoformat(),
        )

    def _build_generation_context(
        self,
        *,
        natural_language_request: str,
        target_country: str,
        run_type: str,
        output_bucket: str | None,
        ctx: UserContext,
        run_id: str | None = None,
    ):
        project_id = int(ctx.project_id) if ctx.project_id and str(ctx.project_id).isdigit() else None
        retriever = DataKnowledgeRetriever(self.db)
        retrieved_context = retriever.retrieve(
            natural_language_request=natural_language_request,
            project_id=project_id,
            country=target_country,
            run_type=run_type,
            output_bucket=output_bucket,
        )
        base_snapshot = PromptContextAssembler.build_base_snapshot(
            country=target_country,
            project_id=project_id,
            natural_language_request=natural_language_request,
            run_type=run_type,
            output_bucket=output_bucket,
            context=retrieved_context,
        )
        request_key = "::".join(
            [
                str(ctx.project_id or ""),
                str(run_id or ""),
                target_country,
                run_type,
                str(output_bucket or ""),
                natural_language_request,
            ]
        )
        shadow_result = build_shadow_trace(
            settings=settings,
            natural_language_request=natural_language_request,
            country=target_country,
            project_id=str(ctx.project_id or "").strip() or None,
            run_type=run_type,
            output_bucket=output_bucket,
            retrieved_context=retrieved_context,
            request_key=request_key,
        )
        fallback_audit_summary = dict(shadow_result.audit_summary)
        deterministic_trace = self._build_attempt_trace(
            shadow_result.trace,
            plan_generation_pass=FINAL_GENERATION_PASS_DETERMINISTIC,
            prompt_injection_mode=PROMPT_INJECTION_NONE,
        )
        deterministic_prompt_context, deterministic_snapshot, hybrid_audit_summary = self._build_attempt_generation_artifacts(
            natural_language_request=natural_language_request,
            target_country=target_country,
            run_type=run_type,
            output_bucket=output_bucket,
            run_id=run_id,
            project_id=project_id,
            retrieved_context=retrieved_context,
            base_snapshot=base_snapshot,
            hybrid_trace=deterministic_trace,
            prompt_injection_mode=PROMPT_INJECTION_NONE,
            plan_generation_pass=FINAL_GENERATION_PASS_DETERMINISTIC,
            source_context=_SOURCE_CONTEXT_DETERMINISTIC_ATTEMPT,
        )
        if shadow_result.trace is None:
            hybrid_audit_summary = fallback_audit_summary
        prompt_context = deterministic_prompt_context
        snapshot = deterministic_snapshot
        trace = shadow_result.trace
        if (
            trace is not None
            and shadow_result.supplemental_prompt_section
            and str(trace.get("configured_mode") or "") in {"hybrid_candidate", "hybrid_enabled"}
            and str(trace.get("effective_mode") or "") in {"hybrid_candidate", "hybrid_enabled"}
            and str(trace.get("prompt_injection_mode") or "") == PROMPT_INJECTION_SUPPLEMENTAL_CANDIDATES_V1
        ):
            attempt_mode = str((trace.get("candidate_attempt") or {}).get("attempted_mode") or trace.get("effective_mode") or "")
            plan_generation_pass = (
                FINAL_GENERATION_PASS_HYBRID_ENABLED
                if attempt_mode == "hybrid_enabled"
                else FINAL_GENERATION_PASS_HYBRID_CANDIDATE
            )
            source_context = (
                _SOURCE_CONTEXT_HYBRID_ENABLED_ATTEMPT
                if attempt_mode == "hybrid_enabled"
                else _SOURCE_CONTEXT_HYBRID_CANDIDATE_ATTEMPT
            )
            try:
                prompt_context, snapshot, hybrid_audit_summary = self._build_attempt_generation_artifacts(
                    natural_language_request=natural_language_request,
                    target_country=target_country,
                    run_type=run_type,
                    output_bucket=output_bucket,
                    run_id=run_id,
                    project_id=project_id,
                    retrieved_context=retrieved_context,
                    base_snapshot=base_snapshot,
                    hybrid_trace=self._build_attempt_trace(
                        trace,
                        plan_generation_pass=plan_generation_pass,
                        prompt_injection_mode=PROMPT_INJECTION_SUPPLEMENTAL_CANDIDATES_V1,
                    ),
                    prompt_injection_mode=PROMPT_INJECTION_SUPPLEMENTAL_CANDIDATES_V1,
                    plan_generation_pass=plan_generation_pass,
                    source_context=source_context,
                    supplemental_prompt_section=shadow_result.supplemental_prompt_section,
                )
            except HTTPException as exc:
                if not self._is_candidate_only_http_exception(exc):
                    raise
                deterministic_snapshot["hybrid_trace"] = self._mark_candidate_attempt(
                    deterministic_snapshot.get("hybrid_trace"),
                    attempted_mode=attempt_mode or None,
                    discarded=True,
                    discard_reason=DISCARD_REASON_CANDIDATE_GENERATION_FAILED,
                    final_effective_mode="deterministic_only",
                    final_prompt_injection_mode=PROMPT_INJECTION_NONE,
                    final_prompt_candidate_count=0,
                    final_generation_pass=FINAL_GENERATION_PASS_DETERMINISTIC_RERUN,
                    fallback_reason=DISCARD_REASON_CANDIDATE_GENERATION_FAILED,
                    fallback_applied=True,
                )
                deterministic_snapshot[_STRUCTURED_SQL_PLAN_PROVENANCE_KEY] = self._build_structured_plan_provenance(
                    plan_generation_pass=FINAL_GENERATION_PASS_DETERMINISTIC_RERUN,
                    prompt_injection_mode=PROMPT_INJECTION_NONE,
                    source_context=_SOURCE_CONTEXT_DETERMINISTIC_RERUN_ATTEMPT,
                )
                hybrid_audit_summary = extract_hybrid_audit_summary({"hybrid_trace": deterministic_snapshot.get("hybrid_trace")})
                prompt_context = deterministic_prompt_context
                snapshot = deterministic_snapshot
        return retrieved_context, deterministic_prompt_context, prompt_context, deterministic_snapshot, snapshot, hybrid_audit_summary

    @staticmethod
    def _serialize_review_event(event) -> ReviewEventView:
        return ReviewEventView(
            decision=event.decision,
            reviewer_user_id=event.reviewer_user_id,
            reviewer_username=event.reviewer_username,
            comment=event.comment,
            from_sql_hash=event.from_sql_hash,
            to_sql_hash=event.to_sql_hash,
            created_at=event.created_at.isoformat(),
        )

    def _persist_sql_example(self, *, run, current, ctx: UserContext) -> None:
        project_id = int(ctx.project_id) if ctx.project_id and str(ctx.project_id).isdigit() else None
        source_namespace = f"approved_sql/{run.country}"
        source_key = f"run:{run.run_id}:sql:{current.sql_hash}"
        existing = self.db.scalar(
            select(DataSqlExample).where(
                DataSqlExample.project_id == project_id,
                DataSqlExample.country == run.country,
                DataSqlExample.source_namespace == source_namespace,
                DataSqlExample.source_key == source_key,
            )
        )
        if existing is not None:
            return
        self.db.add(
            DataSqlExample(
                project_id=project_id,
                country=run.country,
                status="draft",
                source_type="approved_sql",
                source_namespace=source_namespace,
                source_key=source_key,
                source_hash=current.sql_hash,
                created_by=ctx.username,
                updated_by=ctx.username,
                natural_language_request=run.natural_language_request,
                run_type=run.run_type,
                output_bucket=run.output_bucket,
                sql_hash=current.sql_hash,
                sql_text=current.sql_text,
                tables_used_json=[],
                fields_used_json=[],
                pattern_summary=f"approved sql example from run {run.run_id}",
                reviewer_username=ctx.username,
                execution_status="executed",
            )
        )

    def _open_error_case(self, *, run, current, ctx: UserContext, error_message: str) -> None:
        project_id = int(ctx.project_id) if ctx.project_id and str(ctx.project_id).isdigit() else None
        source_namespace = f"error_case/{run.country}"
        source_key = f"run:{run.run_id}"
        existing = self.db.scalar(
            select(DataSqlErrorCase).where(
                DataSqlErrorCase.project_id == project_id,
                DataSqlErrorCase.country == run.country,
                DataSqlErrorCase.source_namespace == source_namespace,
                DataSqlErrorCase.source_key == source_key,
            )
        )
        if existing is None:
            existing = DataSqlErrorCase(
                project_id=project_id,
                country=run.country,
                status="open",
                source_type="error_case",
                source_namespace=source_namespace,
                source_key=source_key,
                source_hash=current.sql_hash,
                created_by=ctx.username,
                updated_by=ctx.username,
                run_id=run.run_id,
                natural_language_request=run.natural_language_request,
                run_type=run.run_type,
                output_bucket=run.output_bucket,
                error_type="execute_failed",
                error_message=error_message,
                failed_sql_hash=current.sql_hash,
                failed_sql_text=current.sql_text,
                detected_tables_json=[],
                detected_fields_json=[],
            )
            self.db.add(existing)
            return
        existing.status = "open"
        existing.updated_by = ctx.username
        existing.error_type = "execute_failed"
        existing.error_message = error_message
        existing.failed_sql_hash = current.sql_hash
        existing.failed_sql_text = current.sql_text
        existing.source_hash = current.sql_hash

    def _resolve_latest_open_error_case(self, *, run, current, comment: str | None, ctx: UserContext) -> None:
        row = self.db.scalar(
            select(DataSqlErrorCase)
            .where(DataSqlErrorCase.run_id == run.run_id, DataSqlErrorCase.status == "open")
            .order_by(desc(DataSqlErrorCase.id))
        )
        if row is None:
            return
        row.status = "resolved"
        row.updated_by = ctx.username
        row.fixed_sql_hash = current.sql_hash
        row.fixed_sql_text = current.sql_text
        row.fix_summary = comment or "revised sql after failed execution"

    @staticmethod
    def _serialize_execution(event) -> ExecutionView:
        payload = event.result_preview_json or {}
        return ExecutionView(
            status=event.status,
            rows_estimated=event.rows_estimated,
            rows_actual=event.rows_actual,
            uids=list(payload.get("uids") or []),
            preview_rows=list(payload.get("preview_rows") or []),
            created_at=event.created_at.isoformat(),
        )

    @staticmethod
    def _serialize_writeback(event) -> WritebackView:
        return WritebackView(
            status=event.status,
            output_bucket=event.output_bucket,
            output_format=event.output_format,
            target_dir=event.target_dir,
            written_uid_count=event.written_uid_count,
            artifact=event.artifact_json,
            created_at=event.created_at.isoformat(),
        )

    @staticmethod
    def _audit(
        *,
        ctx: UserContext,
        event_type: str,
        action: str,
        run,
        sql_hash: str | None,
        status: str = "success",
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        record_runtime_audit_event(
            user=ctx,
            event_type=event_type,
            action=action,
            status=status,
            resource_type="data_agent_run",
            resource_id=run.run_id,
            metadata={
                "run_id": run.run_id,
                "run_type": run.run_type,
                "country": run.country,
                "sql_kind": run.sql_kind,
                "sql_hash": sql_hash,
                "approved_sql_hash": run.approved_sql_hash,
                "output_bucket": run.output_bucket,
                "output_format": run.output_format,
                **(extra_metadata or {}),
            },
        )
