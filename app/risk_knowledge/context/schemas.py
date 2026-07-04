"""Schemas for PR-A Risk QA context isolation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.risk_knowledge.service.schemas import EvidenceTraceItem, RiskQaWarning


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContextBuildRequest(_StrictModel):
    task_type: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    selected_evidence_ids: list[str] = Field(default_factory=list)


class ContextBuildResult(_StrictModel):
    task_type: str = Field(..., min_length=1)
    allowed_context_sources: list[str] = Field(default_factory=list)
    blocked_context_sources: list[str] = Field(default_factory=list)
    context_items: list[EvidenceTraceItem] = Field(default_factory=list)
    context_hash: str = Field(..., min_length=1)
    isolation_warnings: list[RiskQaWarning] = Field(default_factory=list)
