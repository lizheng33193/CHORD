"""Schemas for deterministic SQL semantic validation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


SemanticValidationStatus = Literal["passed", "blocked", "warning", "needs_human_review"]
SemanticViolationSeverity = Literal["info", "warning", "error", "critical"]


class SqlSemanticValidationRequest(_StrictModel):
    query: str = ""
    sql: str = Field(..., min_length=1)
    structured_sql_plan: dict[str, Any] = Field(default_factory=dict)
    business_context: dict[str, Any] = Field(default_factory=dict)
    expected_country: str | None = None
    expected_uid_scope: str | None = None
    expected_time_window: str | None = None
    allowed_tables: list[str] = Field(default_factory=list)
    canonical_field_policy_refs: dict[str, Any] = Field(default_factory=dict)


class SqlSemanticViolation(_StrictModel):
    code: str = Field(..., min_length=1)
    severity: SemanticViolationSeverity
    message: str = Field(..., min_length=1)
    field: str | None = None
    table: str | None = None
    suggestion: str = Field(..., min_length=1)
    blocking: bool = False


class SqlSemanticValidationResult(_StrictModel):
    validation_status: SemanticValidationStatus = "passed"
    violations: list[SqlSemanticViolation] = Field(default_factory=list)
    requires_human_review: bool = False
