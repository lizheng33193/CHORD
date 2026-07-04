"""Internal schemas for the PR-A Risk QA pipeline."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.risk_knowledge.evidence.schemas import RiskEvidenceBundle
from app.risk_knowledge.service.schemas import EvidenceTraceItem, RenderedCitation, RiskQaWarning


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RiskQaRequest(_StrictModel):
    query: str = Field(..., min_length=1)
    kb_id: str = Field(..., min_length=1)
    user_id: str | None = None
    session_id: str | None = None
    document_id: str | None = None
    version_id: str | None = None
    intent: str = "risk_knowledge_qa"
    source: str = "nl_chat"
    answer_style: Literal["concise", "detailed"] = "concise"
    require_citation: bool = True


class EvidenceSufficiencyResult(_StrictModel):
    status: Literal["grounded", "partial", "insufficient_evidence"]
    reason: str = Field(..., min_length=1)
    warnings: list[RiskQaWarning] = Field(default_factory=list)


class CitationValidationResult(_StrictModel):
    passed: bool
    citations: list[RenderedCitation] = Field(default_factory=list)
    warnings: list[RiskQaWarning] = Field(default_factory=list)
    blockers: list[RiskQaWarning] = Field(default_factory=list)
    used_citation_ids: list[str] = Field(default_factory=list)


class RiskQaPipelineResult(_StrictModel):
    answer: str = Field(..., min_length=1)
    answer_type: Literal["grounded_answer", "refusal"]
    should_answer: bool
    refusal_reason: str | None = None
    grounding_status: Literal["grounded", "partial", "insufficient_evidence"]
    citations: list[RenderedCitation] = Field(default_factory=list)
    evidence_trace: list[EvidenceTraceItem] = Field(default_factory=list)
    retrieval_snapshot_id: str | None = None
    blocked_context_sources: list[str] = Field(default_factory=list)
    context_hash: str | None = None
    warnings: list[RiskQaWarning] = Field(default_factory=list)
    used_citation_ids: list[str] = Field(default_factory=list)
    diagnostics: dict[str, object] = Field(default_factory=dict)
    evidence_bundle: RiskEvidenceBundle
