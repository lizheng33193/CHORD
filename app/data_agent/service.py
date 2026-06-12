"""Service layer for Data Agent SQL HITL."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.auth.permissions import normalize_country_scope_value, require_country_access, require_permissions
from app.core.audit import record_runtime_audit_event
from app.core.user_context import UserContext
from app.data_agent.repository import DataAgentRepository
from app.data_agent.safety import resolve_country_names, run_sql_safety_gate
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
from data_acquisition_agent.executor import (
    enforce_pre_execution_gates,
    execute_query,
    precheck_row_count,
    run_execute_pipeline,
)
from data_acquisition_agent.manifest import load_manifest
from data_acquisition_agent.schemas import ExecuteRequest, GenerateRequest, TargetAction, TargetCountry


_UID_FIELD_CANDIDATES = {"uid", "userid", "useruuid", "customerid"}


def _normalize_column_name(name: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name or "").strip().lower())


def _generate_sql_response(*, natural_language_request: str, target_country: str, target_action: str = "extract") -> dict[str, Any]:
    from data_acquisition_agent.orchestrator import DataAcquisitionOrchestrator

    _normalized_country, full_country = resolve_country_names(target_country)
    request = GenerateRequest(
        natural_language_request=natural_language_request,
        target_country=TargetCountry(full_country),
        target_action=TargetAction(target_action),
    )
    response = DataAcquisitionOrchestrator().generate(request)
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
    target_dir = None
    filenames = payload.get("filenames") or []
    if filenames:
        target_dir = str((filenames[0].rsplit("/", 1)[0]) if "/" in filenames[0] else "")
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
        "target_dir": target_dir,
        "written_uid_count": payload.get("total_uids"),
    }


class DataAgentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = DataAgentRepository(db)

    def create_run(self, *, ctx: UserContext, body: DataAgentRunCreateRequest) -> DataAgentRunDetail:
        require_permissions(ctx, ("data:query:generate", "data:query:view_sql"))
        target_country = normalize_country_scope_value(body.target_country) or body.target_country.lower()
        require_country_access(ctx, target_country, project_id=ctx.project_id)

        generated = _generate_sql_response(
            natural_language_request=body.natural_language_request,
            target_country=target_country,
            target_action=body.target_action,
        )
        sql_text = str(generated.get("sql") or "").strip()
        sql_kind = str(generated.get("sql_kind") or "query_only")
        safety_result = run_sql_safety_gate(sql_text, sql_kind, target_country)
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
            sql_text=sql_text,
            sql_hash=safety_result["sql_hash"],
            source="agent_generated",
            sql_kind=sql_kind,
            safety_status=safety_result["status"],
            safety_result_json=safety_result,
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
        require_permissions(ctx, ("data:query:review",))
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
        require_permissions(ctx, ("data:query:review",))
        run = self._get_scoped_run(ctx, run_id)
        current = self.repo.get_sql_version(run.current_sql_version_id)
        previous_hash = run.approved_sql_hash
        safety_result = run_sql_safety_gate(body.sql_text, run.sql_kind or "query_only", run.country)
        version = self.repo.add_sql_version(
            run_id=run.run_id,
            version_no=self.repo.next_version_no(run.run_id),
            sql_text=body.sql_text.strip(),
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
        generated = _generate_sql_response(
            natural_language_request=revised_request,
            target_country=run.country,
            target_action="extract",
        )
        sql_text = str(generated.get("sql") or "").strip()
        sql_kind = str(generated.get("sql_kind") or run.sql_kind or "query_only")
        safety_result = run_sql_safety_gate(sql_text, sql_kind, run.country)
        version = self.repo.add_sql_version(
            run_id=run.run_id,
            version_no=self.repo.next_version_no(run.run_id),
            sql_text=sql_text,
            sql_hash=safety_result["sql_hash"],
            source="agent_revised",
            sql_kind=sql_kind,
            safety_status=safety_result["status"],
            safety_result_json=safety_result,
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
                self.db.commit()
                self._audit(ctx=ctx, event_type="data.query.executed", action="execute", run=run, sql_hash=current.sql_hash)
                self._audit(ctx=ctx, event_type="data.bucket.writeback", action="writeback", run=run, sql_hash=current.sql_hash)
        except HTTPException:
            run.status = "failed"
            run.updated_at = datetime.utcnow()
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
    def _audit(*, ctx: UserContext, event_type: str, action: str, run, sql_hash: str | None, status: str = "success") -> None:
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
            },
        )

