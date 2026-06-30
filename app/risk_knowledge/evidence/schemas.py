"""Evidence schemas for M2D-11."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.risk_knowledge.retrieval.schemas import RetrievalScopeType


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceSelectionConfig(_StrictModel):
    max_evidence_count: int = Field(default=6, ge=1)
    min_evidence_count: int = Field(default=1, ge=1)
    min_rerank_score: float = 0.2
    max_total_chars: int = Field(default=6000, ge=1)
    dedup_by_content_hash: bool = True


class SelectedEvidence(_StrictModel):
    evidence_id: str = Field(..., min_length=1)
    candidate_id: str = Field(..., min_length=1)
    chunk_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    version_id: str = Field(..., min_length=1)
    manifest_index_id: str = Field(..., min_length=1)
    content_hash: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    section_path: list[str] = Field(default_factory=list)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    retrieval_fused_score: float
    retrieval_fused_rank: int = Field(..., ge=1)
    rerank_score: float
    rerank_rank: int = Field(..., ge=1)
    selected_rank: int = Field(..., ge=1)
    matched_channels: list[str] = Field(default_factory=list)


class EvidenceSelectionResult(_StrictModel):
    selected_evidence: list[SelectedEvidence] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class EvidenceGateStatus(str, Enum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    AMBIGUOUS = "ambiguous"
    FAILED = "failed"


class EvidenceGateReason(str, Enum):
    NO_CANDIDATES = "no_candidates"
    NO_RERANK_HITS = "no_rerank_hits"
    BELOW_MIN_SCORE = "below_min_score"
    BELOW_MIN_EVIDENCE_COUNT = "below_min_evidence_count"
    INSUFFICIENT_RELEVANCE = "insufficient_relevance"
    EMPTY_EVIDENCE_TEXT = "empty_evidence_text"
    PROVIDER_FAILURE = "provider_failure"
    SUFFICIENT = "sufficient"


class EvidenceGateDecision(_StrictModel):
    should_answer: bool
    status: EvidenceGateStatus
    reason: EvidenceGateReason
    confidence: float = 0.0
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class Citation(_StrictModel):
    citation_id: str = Field(..., min_length=1)
    evidence_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    version_id: str = Field(..., min_length=1)
    chunk_id: str = Field(..., min_length=1)
    content_hash: str = Field(..., min_length=1)
    section_path: list[str] = Field(default_factory=list)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    manifest_index_id: str = Field(..., min_length=1)
    evidence_rank: int = Field(..., ge=1)


class RiskEvidenceBundle(_StrictModel):
    query: str = Field(..., min_length=1)
    normalized_query: str = Field(..., min_length=1)
    kb_id: str = Field(..., min_length=1)
    scope_type: RetrievalScopeType
    active_manifest_index_ids: list[str] = Field(default_factory=list)
    retrieval_diagnostics: dict[str, Any] = Field(default_factory=dict)
    rerank_provider: str = Field(..., min_length=1)
    rerank_model: str = Field(..., min_length=1)
    selected_evidence: list[SelectedEvidence] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    gate_decision: EvidenceGateDecision
    should_answer: bool
    refusal_reason: str | None = None
