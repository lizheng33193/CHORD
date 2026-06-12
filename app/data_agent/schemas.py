"""Pydantic contracts for Data Agent SQL HITL."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


RunType = Literal["cohort_query", "bucket_writeback"]
RunStatus = Literal["draft_generated", "awaiting_review", "revising", "approved", "rejected", "executing", "executed", "failed", "cancelled"]
SafetyStatus = Literal["passed", "blocked", "review_only"]
SqlSource = Literal["agent_generated", "manual_edited", "agent_revised"]


class DataAgentRunCreateRequest(BaseModel):
    natural_language_request: str = Field(..., min_length=1, max_length=2000)
    target_country: str = Field(..., min_length=2, max_length=32)
    run_type: RunType
    target_action: str = "extract"
    output_bucket: Literal["app", "behavior", "credit"] | None = None
    output_format: Literal["csv", "json"] | None = None
    uid_column: str = "uid"
    overwrite: bool = True

    @model_validator(mode="after")
    def _validate_writeback_fields(self):
        if self.run_type == "bucket_writeback":
            if not self.output_bucket or not self.output_format:
                raise ValueError("bucket_writeback requires output_bucket and output_format")
        return self


class DataAgentReviewActionRequest(BaseModel):
    comment: str | None = None


class DataAgentEditRequest(BaseModel):
    sql_text: str = Field(..., min_length=1)
    comment: str | None = None


class DataAgentReviseRequest(BaseModel):
    comment: str = Field(..., min_length=1)


class SQLVersionView(BaseModel):
    version_id: int
    version_no: int
    sql_text: str | None = None
    sql_hash: str
    source: SqlSource
    sql_kind: str
    safety_status: SafetyStatus
    safety_result: dict[str, Any]
    created_by: str
    created_at: str


class ReviewEventView(BaseModel):
    decision: str
    reviewer_user_id: int | None = None
    reviewer_username: str
    comment: str | None = None
    from_sql_hash: str | None = None
    to_sql_hash: str | None = None
    created_at: str


class ExecutionView(BaseModel):
    status: str
    rows_estimated: int | None = None
    rows_actual: int | None = None
    uids: list[str] = Field(default_factory=list)
    preview_rows: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str | None = None


class WritebackView(BaseModel):
    status: str
    output_bucket: str
    output_format: str
    target_dir: str | None = None
    written_uid_count: int | None = None
    artifact: dict[str, Any] | None = None
    created_at: str | None = None


class DataAgentRunDetail(BaseModel):
    run_id: str
    natural_language_request: str
    target_country: str
    run_type: RunType
    status: RunStatus
    sql_kind: str | None = None
    approved_sql_hash: str | None = None
    output_bucket: str | None = None
    output_format: str | None = None
    current_sql: SQLVersionView | None = None
    review_events: list[ReviewEventView] = Field(default_factory=list)
    execution: ExecutionView | None = None
    writeback: WritebackView | None = None
    created_at: str
    updated_at: str


class DataAgentRunSummary(BaseModel):
    run_id: str
    natural_language_request: str
    target_country: str
    run_type: RunType
    status: RunStatus
    sql_kind: str | None = None
    approved_sql_hash: str | None = None
    current_sql: SQLVersionView | None = None
    created_at: str
    updated_at: str


class DataAgentRunListResponse(BaseModel):
    runs: list[DataAgentRunSummary]

