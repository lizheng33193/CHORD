"""Pydantic v2 schemas for Orchestrator Agent inputs / outputs / sessions."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# 6 国短码（与 docs/skills/orchestrator/*.md 文件名对齐）
# 注意：与 data_acquisition_agent.TargetCountry 全称（mexico/...）不一致，
# V1 只 mexico 走真，其它 5 国 query_data 直接 reject（见 Task 1.5）。
CountryCode = Literal["th", "mx", "co", "pe", "cl", "br"]

# Profile 模块（与 AnalysisOrchestrator.SUPPORTED_MODULES 对齐）
ProfileModule = Literal["app", "behavior", "credit", "comprehensive", "product", "ops"]
BucketName = Literal["app", "behavior", "credit"]
KnownIntent = Literal[
    "answer_from_workspace",
    "profile_uid",
    "profile_batch",
    "need_clarification",
    "query_data_then_profile",
    "run_trace",
    "general_chat",
]
AnswerMode = Literal["workspace_evidence_answer", "tool_execution", "general_chat"]
PlanStepStatus = Literal["pending", "running", "awaiting_resolution", "done", "skipped", "blocked", "failed"]
BucketStatus = Literal["available", "missing", "invalid", "unsupported"]


# ===== Top-level chat request =====

class OrchestratorChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    session_id: Optional[str] = None


# ===== 6 工具的 Input / Output Schemas =====

class ParseUidFileInput(BaseModel):
    file_path: str = Field(..., description="UID 文件本地路径，必须在 data/id_files/ 下")


class ParseUidFileOutput(BaseModel):
    uids: list[str]
    source_path: str
    duplicates_removed: int


class RunProfileInput(BaseModel):
    uids: list[str] = Field(..., min_length=1, max_length=200)
    app_time: Optional[str] = Field(None, description="ISO8601 格式 application_time；未提供时由模块走默认口径")
    modules: Optional[list[ProfileModule]] = None  # None = 默认 ["app"]
    strict_data_mode: bool = False


class RunProfileOutput(BaseModel):
    results: list[dict[str, Any]]
    cache_hits: int = 0
    cache_misses: int = 0


class RunTraceInput(BaseModel):
    uid: str
    days: int = Field(7, ge=1, le=90)


class RunTraceOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    uid: Optional[str] = None
    status: str = "unknown"
    events: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class QueryDataInput(BaseModel):
    request: str = Field(..., min_length=1, max_length=2000)
    country: CountryCode


class QueryDataOutput(BaseModel):
    uids: list[str]
    rows_actual: int
    sql_text: str          # 已脱敏
    rows_estimated: int = -1


class RepairProfileDataInput(BaseModel):
    uids: list[str] = Field(..., min_length=1, max_length=200)
    country: str
    bucket: BucketName
    reason: str = Field(..., min_length=1, max_length=1000)


class RepairProfileDataOutput(BaseModel):
    bucket: BucketName
    requested_uids: list[str]
    written_uids: list[str]
    filenames: list[str]
    sql_text: str
    rows_estimated: int = -1
    rows_actual: int = 0


class MemoryWriteInput(BaseModel):
    key: str = Field(..., pattern=r"^[a-zA-Z0-9_/.-]+$", max_length=200)
    value: str = Field(..., max_length=20000)


class MemoryWriteOutput(BaseModel):
    ok: bool
    path: str


class MemoryReadInput(BaseModel):
    key_pattern: str = Field(..., max_length=200)


class MemoryReadOutput(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


class RequestUnderstanding(BaseModel):
    intent: KnownIntent
    route_label: str
    rewritten_goal: str
    focus: list[str] = Field(default_factory=list)
    requires_tools: bool
    route_reason: str
    answer_mode: AnswerMode
    missing_slots: list[str] = Field(default_factory=list)
    clarification_prompt: str | None = None
    candidate_defaults: dict[str, Any] = Field(default_factory=dict)


class NormalizedRequest(BaseModel):
    intent: KnownIntent
    country: str | None = None
    uids: list[str] = Field(default_factory=list)
    uid_file_path: str | None = None
    modules: list[ProfileModule] = Field(default_factory=list)
    trace_days: int = 7
    application_time_hint: str | None = None
    request_summary: str
    query_request: str | None = None
    read_only: bool = False
    request_understanding: RequestUnderstanding | None = None


class BucketAvailability(BaseModel):
    status: BucketStatus
    available: bool
    usable_for_profile: bool = False
    checked_sources: list[str] = Field(default_factory=list)
    source_type: str
    source_shape: str | None = None
    path: str | None = None
    detail: str | None = None
    quality_score: float | None = None
    weak_reasons: list[str] = Field(default_factory=list)
    row_count: int | None = None


class UidAvailability(BaseModel):
    uid: str
    app: BucketAvailability
    behavior: BucketAvailability
    credit: BucketAvailability
    available_buckets: list[BucketName] = Field(default_factory=list)
    missing_buckets: list[BucketName] = Field(default_factory=list)


class DataAvailability(BaseModel):
    country: str | None = None
    checked_uids: list[str] = Field(default_factory=list)
    per_uid: list[UidAvailability] = Field(default_factory=list)


class PlanStep(BaseModel):
    step_id: str
    title: str
    kind: str
    status: PlanStepStatus = "pending"
    user_visible_reason: str = ""
    tool_name: str | None = None
    tool_call_id: str | None = None
    result_summary: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    resolution_type: str | None = None
    resolution_prompt: str | None = None
    resolution_options: list[str] = Field(default_factory=list)
    resolution_required_slots: list[str] = Field(default_factory=list)
    resolution_candidate_defaults: dict[str, Any] = Field(default_factory=dict)


class ExecutionPlan(BaseModel):
    execution_id: str
    request_summary: str
    intent: KnownIntent
    request_understanding: RequestUnderstanding | None = None
    availability: DataAvailability | None = None
    steps: list[PlanStep] = Field(default_factory=list)


class ReviewResult(BaseModel):
    status: Literal["pass", "warning", "fail"]
    issues: list[dict[str, Any]] = Field(default_factory=list)
    can_answer: bool
    confidence_impact: str | None = None


class ExecutionTraceRecord(BaseModel):
    turn_id: str | None = None
    run_id: str | None = None
    execution_id: str
    trace_id: str | None = None
    request_id: str | None = None
    prompt: str
    request_summary: str
    intent: KnownIntent
    request_understanding: RequestUnderstanding | None = None
    availability: DataAvailability | None = None
    steps: list[PlanStep] = Field(default_factory=list)
    review: ReviewResult | None = None
    final_status: Literal["running", "completed", "blocked", "error"] = "running"
    final_message: str | None = None
    internal_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


# ===== Session 持久化 schemas =====

class ToolCallRecord(BaseModel):
    turn_id: str | None = None
    run_id: str | None = None
    trace_id: str | None = None
    tool_name: str
    tool_call_id: str
    input: dict[str, Any]
    output: dict[str, Any] | None = None
    status: Literal["pending", "running", "done", "error", "cancelled"]
    started_at: datetime
    finished_at: datetime | None = None


class OrchestratorMessage(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str
    turn_id: str | None = None
    run_id: str | None = None
    tool_call_id: str | None = None
    timestamp: datetime


class RunEvent(BaseModel):
    event_id: str
    event_seq: int
    session_id: str
    turn_id: str
    run_id: str
    event_type: str
    timestamp: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class PendingAckState(BaseModel):
    ack_id: str
    tool_call_id: str
    step_id: str | None = None
    tool_name: str | None = None
    title: str | None = None
    sql_text: str | None = None
    preview_rows: list[dict[str, Any]] = Field(default_factory=list)
    preview_truncated: bool = False
    rows_estimated: int | None = None
    created_at: datetime
    updated_at: datetime | None = None


class PendingResolutionState(BaseModel):
    resolution_id: str
    step_id: str
    resolution_type: str
    title: str | None = None
    message: str | None = None
    options: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None


class TurnRunRecord(BaseModel):
    run_id: str
    trace_id: str | None = None
    status: str = "queued"
    completeness: Literal["none", "partial", "complete"] = "none"
    summary: str | None = None
    review_status: str | None = None
    final_message: str | None = None
    tool_call_ids: list[str] = Field(default_factory=list)
    pending_ack: PendingAckState | None = None
    pending_resolution: PendingResolutionState | None = None
    started_at: datetime
    ended_at: datetime | None = None
    last_event_seq: int = 0


class ConversationTurn(BaseModel):
    turn_id: str
    client_turn_id: str | None = None
    session_id: str
    user_message: OrchestratorMessage
    assistant_message: OrchestratorMessage | None = None
    runs: list[TurnRunRecord] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "running"
    collapsed: bool = False
    legacy: bool = False
    created_at: datetime
    updated_at: datetime


class OrchestratorSession(BaseModel):
    session_id: str
    created_at: datetime
    updated_at: datetime
    user_id: str = "local-default-user"
    project_id: str = "agent-user-profile-fork"
    country: str | None = None
    rolling_summary: str | None = None
    active_entities: dict[str, Any] = Field(default_factory=dict)
    last_memory_sync_at: datetime | None = None
    messages: list[OrchestratorMessage] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    execution_traces: list[ExecutionTraceRecord] = Field(default_factory=list)
    turns: list[ConversationTurn] = Field(default_factory=list)
    run_events: list[RunEvent] = Field(default_factory=list)
    total_tokens: int = 0
    final_message: str | None = None
    confidence: float | None = None
    status: Literal["active", "completed", "error", "budget_exceeded"] = "active"
    active_turn_id: str | None = None
    active_run_id: str | None = None
    active_run_status: str | None = None
    # 同 session 内任一 query_data ACK 被拒绝则置 True，后续 query_data 直接 reject
    query_cancelled: bool = False
    # 连续工具失败计数，达 K=3 强制结束 session
    consecutive_failures: int = 0
