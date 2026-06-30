"""Normalized parser-side contracts for M2D-6."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.knowledge_base.schemas import SourceType


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceDocumentRef(_StrictModel):
    kb_id: str = Field(..., min_length=1)
    doc_id: str = Field(..., min_length=1)
    version_id: str = Field(..., min_length=1)
    file_path: str = Field(..., min_length=1)
    doc_name: str = Field(..., min_length=1)
    source_type: SourceType


class RawParsedChunk(_StrictModel):
    chunk_order: int = Field(..., ge=1)
    raw_content: str = Field(..., min_length=1)
    chunk_type: str | None = None
    title: str | None = None
    section_title: str | None = None
    section_path: list[str] = Field(default_factory=list)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    position: dict[str, Any] | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_page_range(self) -> "RawParsedChunk":
        if self.page_start is not None and self.page_end is not None and self.page_end < self.page_start:
            raise ValueError("page_end must be >= page_start")
        return self


class ParsedDocument(_StrictModel):
    source: SourceDocumentRef
    parser_name: str = Field(..., min_length=1)
    parser_version: str | None = None
    raw_chunks: list[RawParsedChunk] = Field(default_factory=list)
    document_metadata: dict[str, Any] = Field(default_factory=dict)
