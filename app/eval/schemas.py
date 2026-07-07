"""Shared schemas for the M5-1 eval foundation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


EvalStatus = Literal["PASS", "WARN", "FAIL", "BLOCKED"]
EvalSeverity = Literal["info", "minor", "major", "critical", "blocker"]
RunnerStatus = Literal["completed", "config_error", "execution_error"]


class EvalCase(_StrictModel):
    case_id: str = Field(..., min_length=1)
    suite: str = Field(..., min_length=1)
    task_type: str = Field(..., min_length=1)
    input: dict[str, Any] = Field(default_factory=dict)
    expected: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    severity: EvalSeverity = "major"
    source: str = "manual"
    created_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("case_id", "suite", "task_type", "source", mode="before")
    @classmethod
    def _normalize_required_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class EvalResult(_StrictModel):
    case_id: str = Field(..., min_length=1)
    suite: str = Field(..., min_length=1)
    status: EvalStatus
    passed: bool
    score: float = 1.0
    metrics: dict[str, Any] = Field(default_factory=dict)
    failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float | None = None
    error_text: str | None = None


class EvalSuite(_StrictModel):
    suite_id: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    case_path: str = Field(..., min_length=1)
    evaluator: str = Field(..., min_length=1)
    blocking: bool = True
    advisory: bool = False


class EvalProfile(_StrictModel):
    profile_id: str = Field(..., min_length=1)
    suites: list[str] = Field(..., min_length=1)
    description: str | None = None
    strict_by_default: bool = False


class EvalReport(_StrictModel):
    run_id: str = Field(..., min_length=1)
    created_at: str = Field(..., min_length=1)
    suite_id: str | None = None
    profile_id: str | None = None
    case_file: str = Field(..., min_length=1)
    strict: bool = False
    overall_status: EvalStatus
    runner_status: RunnerStatus
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    results: list[EvalResult] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    artifact_paths: dict[str, str] = Field(default_factory=dict)
