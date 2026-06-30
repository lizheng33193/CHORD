"""Schemas for M2D-11 reranking."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RerankCandidateInput(_StrictModel):
    candidate_id: str = Field(..., min_length=1)
    chunk_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    version_id: str = Field(..., min_length=1)
    manifest_index_id: str = Field(..., min_length=1)
    content_hash: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    section_path: str | None = None
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    retrieval_fused_score: float
    retrieval_fused_rank: int = Field(..., ge=1)


class RerankRequest(_StrictModel):
    query: str = Field(..., min_length=1)
    candidates: list[RerankCandidateInput] = Field(default_factory=list)
    model: str = Field(..., min_length=1)
    top_n: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _validate_query(self) -> "RerankRequest":
        if not self.query.strip():
            raise ValueError("query must not be blank")
        return self


class RerankItem(_StrictModel):
    candidate_index: int | None = Field(default=None, ge=0)
    candidate_id: str | None = Field(default=None, min_length=1)
    chunk_id: str = Field(..., min_length=1)
    rerank_score: float
    rerank_rank: int = Field(..., ge=1)


class RerankResult(_StrictModel):
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    items: list[RerankItem] = Field(default_factory=list)
