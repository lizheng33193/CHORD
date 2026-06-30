"""M2D-7 metadata and evidence contracts."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.knowledge_base.schemas import KnowledgeChunk


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RiskEvidenceScore(_StrictModel):
    fulltext_score: float | None = None
    vector_score: float | None = None
    rerank_score: float | None = None
    final_score: float | None = None


class EvidenceUsage(str, Enum):
    SUPPORTING_EVIDENCE = "supporting_evidence"


class RiskEvidence(_StrictModel):
    evidence_id: str = Field(..., min_length=1)
    kb_id: str = Field(..., min_length=1)
    doc_id: str = Field(..., min_length=1)
    doc_title: str = Field(..., min_length=1)
    version_id: str = Field(..., min_length=1)
    chunk_id: str = Field(..., min_length=1)
    section_title: str | None = None
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    score: RiskEvidenceScore | None = None
    text: str = Field(..., min_length=1)
    usage: EvidenceUsage


class MetadataBuildResult(_StrictModel):
    chunks: list[KnowledgeChunk] = Field(default_factory=list)


class EvidenceBuildResult(_StrictModel):
    evidence: list[RiskEvidence] = Field(default_factory=list)
