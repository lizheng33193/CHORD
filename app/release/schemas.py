"""Schemas for Pre-M3 release gate reporting."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


ReleaseGateStatus = Literal["PASS", "WARN", "FAIL", "BLOCKED"]
ReleaseGateCheckStatus = Literal["PASS", "WARN", "FAIL", "BLOCKED", "NOT_RUN"]
ReleaseGateProfile = Literal["pr_acceptance", "production_release"]


class ReleaseGateCheckResult(_StrictModel):
    check_name: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    status: ReleaseGateCheckStatus
    summary: str = Field(..., min_length=1)
    blocking: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ReleaseGateReport(_StrictModel):
    gate_name: str = "pre_m3_release_gate"
    profile: ReleaseGateProfile
    release_gate_status: ReleaseGateStatus
    checks: list[ReleaseGateCheckResult] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendation: str = Field(..., min_length=1)
