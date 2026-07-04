"""Schemas for the M2D-12 and PR-A risk knowledge service boundary."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.knowledge_base.config import DEFAULT_RISK_KB_ID
from app.risk_knowledge.evidence.schemas import Citation, RiskEvidenceBundle
from app.risk_knowledge.traces import RiskEvidenceBuildTrace


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RiskKnowledgeQuery(_StrictModel):
    query: str = Field(..., min_length=1)
    kb_id: str = Field(default=DEFAULT_RISK_KB_ID, min_length=1)
    user_id: str | None = None
    session_id: str | None = None
    document_id: str | None = None
    version_id: str | None = None
    intent: Literal["risk_knowledge_qa", "profile_explanation"] = "risk_knowledge_qa"
    source: str = "nl_chat"
    answer_style: Literal["concise", "detailed"] = "concise"

    @field_validator("query")
    @classmethod
    def _validate_query(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("query must not be blank")
        return normalized

    @field_validator("kb_id", mode="before")
    @classmethod
    def _default_kb_id(cls, value: str | None) -> str:
        normalized = str(value or "").strip()
        return normalized or DEFAULT_RISK_KB_ID


class RenderedCitation(_StrictModel):
    citation_id: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    document_title: str | None = None
    version_id: str = Field(..., min_length=1)
    chunk_id: str = Field(..., min_length=1)
    evidence_id: str | None = None
    source_type: Literal["risk_domain_knowledge"] = "risk_domain_knowledge"
    section_path: str | None = None
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    quote: str | None = None


class RiskQaWarning(_StrictModel):
    code: str = Field(..., min_length=1)
    severity: Literal["info", "warning", "blocker"]
    message: str = Field(..., min_length=1)
    detail: dict[str, object] = Field(default_factory=dict)


class EvidenceTraceItem(_StrictModel):
    evidence_id: str = Field(..., min_length=1)
    source_type: Literal[
        "risk_domain_knowledge",
        "data_knowledge",
        "sql_examples",
        "sql_error_cases",
        "catalog_grounding",
        "memory",
    ]
    document_id: str | None = None
    document_name: str | None = None
    document_version: str | None = None
    section_title: str | None = None
    section_path: list[str] = Field(default_factory=list)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    chunk_id: str | None = None
    evidence_text: str = Field(..., min_length=1)
    score: float | None = None
    rerank_score: float | None = None
    confidence: float | None = None
    used_in_answer: bool = False
    citation_label: str | None = None
    warnings: list[str] = Field(default_factory=list)


class EvidenceContextItem(_StrictModel):
    citation_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    document_title: str | None = None
    section_path: list[str] = Field(default_factory=list)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    rerank_score: float
    evidence_rank: int = Field(..., ge=1)


class EvidenceContext(_StrictModel):
    query: str = Field(..., min_length=1)
    evidence_items: list[EvidenceContextItem] = Field(default_factory=list)
    citation_map: dict[str, Citation] = Field(default_factory=dict)
    total_chars: int = Field(default=0, ge=0)


class GroundedAnswerRequest(_StrictModel):
    query: str = Field(..., min_length=1)
    evidence_context: EvidenceContext
    answer_style: Literal["concise", "detailed"] = "concise"
    language: str = "zh"


class GroundedAnswerResult(_StrictModel):
    answer: str = Field(..., min_length=1)
    used_citation_ids: list[str] = Field(default_factory=list)
    provider: str | None = None
    model: str | None = None


class RouteDecision(_StrictModel):
    should_route: bool
    reason: str = Field(..., min_length=1)
    target_kb_id: str | None = None


class RiskKnowledgeAnswer(_StrictModel):
    type: Literal["risk_knowledge_answer"] = "risk_knowledge_answer"
    schema_version: str = "risk_knowledge_answer.v1"
    query: str = Field(..., min_length=1)
    normalized_query: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    answer_type: Literal["grounded_answer", "refusal"]
    should_answer: bool
    refusal_reason: str | None = None
    evidence_bundle: RiskEvidenceBundle
    grounding_status: Literal["grounded", "partial", "insufficient_evidence"] = "grounded"
    citations: list[RenderedCitation] = Field(default_factory=list)
    evidence_trace: list[EvidenceTraceItem] = Field(default_factory=list)
    retrieval_snapshot_id: str | None = None
    blocked_context_sources: list[str] = Field(default_factory=list)
    context_hash: str | None = None
    warnings: list[RiskQaWarning] = Field(default_factory=list)
    used_citation_ids: list[str] = Field(default_factory=list)
    diagnostics: dict[str, object] = Field(default_factory=dict)


class RiskKnowledgeAnswerTrace(_StrictModel):
    query: RiskKnowledgeQuery
    build_trace: RiskEvidenceBuildTrace
    answer: RiskKnowledgeAnswer


class ProfileExplanationRequest(_StrictModel):
    profile_facts: list[str] = Field(..., min_length=1)
    kb_id: str = Field(default=DEFAULT_RISK_KB_ID, min_length=1)
    user_id: str | None = None
    source: str = "profile_explanation"
    answer_style: Literal["concise", "detailed"] = "concise"
