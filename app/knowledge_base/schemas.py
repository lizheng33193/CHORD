"""Pydantic contracts for the M2D knowledge-base skeleton."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KnowledgeBaseType(str, Enum):
    RISK_DOMAIN = "risk_domain"


class KnowledgeBaseStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"
    DELETED = "deleted"


class SourceType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"
    MARKDOWN = "markdown"
    TXT = "txt"
    HTML = "html"
    JSON = "json"
    XLSX = "xlsx"
    XLS = "xls"
    PPTX = "pptx"
    UNKNOWN = "unknown"


class DocumentStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"
    DELETED = "deleted"


class DocumentVersionStatus(str, Enum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    INDEXED = "indexed"
    ACTIVE = "active"
    REINDEXING = "reindexing"
    FAILED = "failed"
    DEPRECATED = "deprecated"
    DELETED = "deleted"


class ChunkStatus(str, Enum):
    PENDING = "pending"
    INDEXED = "indexed"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    DELETED = "deleted"


class IngestJobStatus(str, Enum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    INDEXED = "indexed"
    ACTIVE = "active"
    REINDEXING = "reindexing"
    FAILED = "failed"
    DEPRECATED = "deprecated"
    DELETED = "deleted"


class IngestStep(str, Enum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    INDEXED = "indexed"
    ACTIVE = "active"
    REINDEXING = "reindexing"
    FAILED = "failed"
    DEPRECATED = "deprecated"
    DELETED = "deleted"


class PermissionScope(str, Enum):
    INTERNAL = "internal"
    RESTRICTED = "restricted"


class KnowledgeBase(_StrictModel):
    kb_id: str = Field(..., min_length=1)
    kb_name: str = Field(..., min_length=1)
    kb_type: KnowledgeBaseType
    description: str | None = None
    status: KnowledgeBaseStatus
    index_alias: str = Field(..., min_length=1)


class KnowledgeDocument(_StrictModel):
    doc_id: str = Field(..., min_length=1)
    kb_id: str = Field(..., min_length=1)
    doc_title: str = Field(..., min_length=1)
    doc_name: str = Field(..., min_length=1)
    source_type: SourceType
    source_uri: str = Field(..., min_length=1)
    current_version_id: str | None = None
    status: DocumentStatus
    permission_scope: PermissionScope = PermissionScope.INTERNAL


class KnowledgeDocumentVersion(_StrictModel):
    version_id: str = Field(..., min_length=1)
    doc_id: str = Field(..., min_length=1)
    kb_id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    file_hash: str = Field(..., min_length=1)
    file_uri: str = Field(..., min_length=1)
    parser_version: str | None = None
    chunker_version: str | None = None
    embedding_model: str | None = None
    embedding_dim: int | None = Field(default=None, ge=1)
    index_name: str | None = None
    status: DocumentVersionStatus


class KnowledgeChunk(_StrictModel):
    chunk_id: str = Field(..., min_length=1)
    kb_id: str = Field(..., min_length=1)
    doc_id: str = Field(..., min_length=1)
    version_id: str = Field(..., min_length=1)
    chunk_order: int = Field(..., ge=1)
    chunk_type: str = Field(..., min_length=1)
    section_title: str | None = None
    section_path: list[str] = Field(default_factory=list)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    content: str = Field(..., min_length=1)
    content_hash: str = Field(..., min_length=1)
    status: ChunkStatus
    es_index_name: str | None = None
    es_doc_id: str | None = None
    embedding_model: str | None = None
    embedding_dim: int | None = Field(default=None, ge=1)
    parser_version: str | None = None
    chunker_version: str | None = None
    permission_scope: PermissionScope = PermissionScope.INTERNAL

    @model_validator(mode="after")
    def _validate_page_range(self) -> "KnowledgeChunk":
        if self.page_start is not None and self.page_end is not None and self.page_start > self.page_end:
            raise ValueError("page_start must be <= page_end")
        return self


class KnowledgeIngestJob(_StrictModel):
    job_id: str = Field(..., min_length=1)
    kb_id: str = Field(..., min_length=1)
    doc_id: str = Field(..., min_length=1)
    version_id: str = Field(..., min_length=1)
    status: IngestJobStatus
    current_step: IngestStep
    error_message: str | None = None
