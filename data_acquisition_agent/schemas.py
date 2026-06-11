"""Pydantic request/response/error schemas for data_acquisition_agent V1.

See docs/specs/data_acquisition_agent.md §5 for field semantics.
Validators (sql/python at-least-one, sql_kind ↔ high_risk_ddl coupling) are
intentionally NOT implemented here — left to Step 4 TDD.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class TargetCountry(str, Enum):
    MEXICO = "mexico"
    INDONESIA = "indonesia"
    PAKISTAN = "pakistan"
    THAILAND = "thailand"
    PHILIPPINES = "philippines"


class TargetAction(str, Enum):
    BUILD_TABLE = "build_table"
    EXTRACT = "extract"
    BUILD_TABLE_AND_EXTRACT = "build_table_and_extract"


class ErrorType(str, Enum):
    BAD_REQUEST = "bad_request"
    PROMPT_TOO_LARGE = "prompt_too_large"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    CREDENTIAL_LEAK = "credential_leak"
    DANGEROUS_CODE = "dangerous_code"
    DDL_POLICY_VIOLATION = "ddl_policy_violation"
    UPSTREAM_LLM_ERROR = "upstream_llm_error"
    # V2 新增（docs/specs/data_acquisition_agent_v2.md §5.3）
    DDL_NOT_SUPPORTED_IN_V2 = "ddl_not_supported_in_v2"
    DB_UNREACHABLE = "db_unreachable"
    QUERY_FAILED = "query_failed"
    RESULT_VALIDATION_FAILED = "result_validation_failed"
    RESULT_TOO_LARGE = "result_too_large"
    OUTPUT_WRITE_FAILED = "output_write_failed"


class GenerateRequest(BaseModel):
    natural_language_request: str = Field(..., description="自然语言取数需求原文")
    target_country: TargetCountry = Field(..., description="目标国家枚举")
    target_action: Optional[TargetAction] = Field(None, description="可选；缺省由 LLM 推断")
    # TODO[Step 4]: validator — natural_language_request 长度上限


class AuditReport(BaseModel):
    """Design Doc §5：extra='allow' 容忍 LLM 多输出字段。"""

    high_risk_ddl: bool = Field(..., description="build_table_script 时必须为 True")
    final_verdict: str = Field(..., description="LLM 最终判定语")

    class Config:
        extra = "allow"


class TokensUsed(BaseModel):
    prompt: Optional[int] = None
    completion: Optional[int] = None


class GenerateMetadata(BaseModel):
    model: str
    tokens_used: Optional[TokensUsed] = None
    token_estimate: int
    knowledge_files_loaded: list[str]
    redaction_events: int
    danger_scan_events: int
    generated_at: str


class GenerateResponse(BaseModel):
    request_id: str
    target_country: TargetCountry
    reasoning_summary: str
    sql: Optional[str] = None
    sql_kind: Optional[Literal["query_only", "build_table_script"]] = None
    python: Optional[str] = None
    audit_report: AuditReport
    metadata: GenerateMetadata

    @model_validator(mode="after")
    def _at_least_one_artifact(self):
        if not (self.sql or self.python):
            raise ValueError("sql and python cannot both be empty")
        return self

    @model_validator(mode="after")
    def _sql_kind_audit_coupling(self):
        if self.sql and not self.sql_kind:
            raise ValueError("sql_kind required when sql is present")
        if self.sql_kind == "build_table_script" and not self.audit_report.high_risk_ddl:
            raise ValueError("build_table_script requires audit_report.high_risk_ddl=True")
        if self.sql_kind == "query_only" and self.audit_report.high_risk_ddl:
            raise ValueError("query_only must not set high_risk_ddl=True")
        return self


class ErrorResponse(BaseModel):
    error_type: ErrorType
    message: str
    request_id: str


# ---------------------------------------------------------------------------
# V2 ExecuteRequest / ExecuteResponse （docs/specs/data_acquisition_agent_v2.md §5）
# ---------------------------------------------------------------------------


class ExecuteRequest(BaseModel):
    """V2 受控执行请求。validators 留 V2 Step 4 TDD（app bucket → csv 强制等）。"""

    approved_sql: str = Field(..., description="分析师审核后的 SQL")
    sql_kind: Literal["query_only", "build_table_script"]
    target_country: TargetCountry
    approved_by: str = Field(..., description="审计 metadata，非安全凭证")
    approval_note: Optional[str] = None
    source_request_id: Optional[str] = Field(None, description="关联 V1 request_id；V2 不回查")
    output_bucket: Literal["app", "behavior", "credit"]
    output_format: Literal["csv", "json"]
    uid_column: str = "uid"
    overwrite: bool = True

    @field_validator("approved_sql")
    @classmethod
    def _approved_sql_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("approved_sql must be non-empty")
        return v

    @model_validator(mode="after")
    def _app_bucket_requires_csv(self):
        if self.output_bucket == "app" and self.output_format != "csv":
            raise ValueError("app bucket requires output_format=csv")
        return self


class ExecuteMetadata(BaseModel):
    executed_at: str
    approved_by: str
    source_request_id: Optional[str] = None
    duration_ms: int
    row_count_total: int


class ExecuteResponse(BaseModel):
    request_id: str
    output_bucket: Literal["app", "behavior", "credit"]
    output_format: Literal["csv", "json"]
    filenames: list[str]
    written_file_count: int
    total_uids: int
    rows_per_uid: dict[str, int]
    metadata: ExecuteMetadata
