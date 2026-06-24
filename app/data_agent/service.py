"""Service layer for Data Agent SQL HITL."""

from __future__ import annotations

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
from app.data_agent.repository import DataAgentRepository
from app.data_agent.safety import resolve_country_names, run_sql_safety_gate
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
from app.data_knowledge.prompt_context import PromptContextAssembler
from app.data_knowledge.retriever import DataKnowledgeRetriever
from app.data_knowledge.models import DataSqlErrorCase, DataSqlExample
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


class DataAgentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = DataAgentRepository(db)

    def create_run(self, *, ctx: UserContext, body: DataAgentRunCreateRequest) -> DataAgentRunDetail:
        require_permissions(ctx, ("data:query:generate", "data:query:view_sql"))
        target_country = normalize_country_scope_value(body.target_country) or body.target_country.lower()
        require_country_access(ctx, target_country, project_id=ctx.project_id)
        _retrieved_context, prompt_context, retrieval_snapshot = self._build_generation_context(
            natural_language_request=body.natural_language_request,
            target_country=target_country,
            run_type=body.run_type,
            output_bucket=body.output_bucket,
            ctx=ctx,
        )

        try:
            generated = _generate_sql_response(
                natural_language_request=body.natural_language_request,
                target_country=target_country,
                target_action=body.target_action,
                knowledge_prompt_context=prompt_context,
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
        safety_result = run_sql_safety_gate(sql_text, sql_kind, target_country)
        safety_result = _append_unsupported_field_warnings(
            safety_result=safety_result,
            sql_text=sql_text,
            retrieval_snapshot=retrieval_snapshot,
        )
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
            source="agent_generated",
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
        )
        self._audit(
            ctx=ctx,
            event_type="data.query.sql_generated",
            action="generate",
            run=run,
            sql_hash=version.sql_hash,
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
        _retrieved_context, prompt_context, retrieval_snapshot = self._build_generation_context(
            natural_language_request=revised_request,
            target_country=run.country,
            run_type=run.run_type,
            output_bucket=run.output_bucket,
            ctx=ctx,
        )
        try:
            generated = _generate_sql_response(
                natural_language_request=revised_request,
                target_country=run.country,
                target_action="extract",
                knowledge_prompt_context=prompt_context,
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
        safety_result = run_sql_safety_gate(sql_text, sql_kind, run.country)
        safety_result = _append_unsupported_field_warnings(
            safety_result=safety_result,
            sql_text=sql_text,
            retrieval_snapshot=retrieval_snapshot,
        )
        version = self.repo.add_sql_version(
            run_id=run.run_id,
            version_no=self.repo.next_version_no(run.run_id),
            sql_text=safety_result["normalized_sql"],
            sql_hash=safety_result["sql_hash"],
            source="agent_revised",
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
        self._audit(ctx=ctx, event_type="data.query.sql_revised", action="revise", run=run, sql_hash=version.sql_hash)
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
        assembler = PromptContextAssembler()
        prompt_context = assembler.assemble(
            natural_language_request=natural_language_request,
            country=target_country,
            run_type=run_type,
            output_bucket=output_bucket,
            context=retrieved_context,
        )
        snapshot = assembler.build_snapshot(
            country=target_country,
            project_id=project_id,
            natural_language_request=natural_language_request,
            run_type=run_type,
            output_bucket=output_bucket,
            context=retrieved_context,
            assembled=prompt_context,
        )
        return retrieved_context, prompt_context, snapshot

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
