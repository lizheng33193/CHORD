from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.knowledge_base.config import (
    DEFAULT_RISK_INDEX_ALIAS,
    DEFAULT_RISK_KB_ID,
    DEFAULT_RISK_KB_NAME,
)
from app.knowledge_base.schemas import (
    ChunkStatus,
    DocumentStatus,
    DocumentVersionStatus,
    IngestJobStatus,
    IngestStep,
    KnowledgeBase,
    KnowledgeBaseStatus,
    KnowledgeBaseType,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    KnowledgeIngestJob,
    PermissionScope,
    SourceType,
)


def test_default_kb_contract_can_be_created() -> None:
    kb = KnowledgeBase(
        kb_id=DEFAULT_RISK_KB_ID,
        kb_name=DEFAULT_RISK_KB_NAME,
        kb_type=KnowledgeBaseType.RISK_DOMAIN,
        description="Risk-domain document knowledge base for M2D.",
        status=KnowledgeBaseStatus.ACTIVE,
        index_alias=DEFAULT_RISK_INDEX_ALIAS,
    )

    assert kb.kb_id == DEFAULT_RISK_KB_ID
    assert kb.status == KnowledgeBaseStatus.ACTIVE


def test_document_allows_empty_current_version_id() -> None:
    document = KnowledgeDocument(
        doc_id="risk_guide",
        kb_id=DEFAULT_RISK_KB_ID,
        doc_title="智能风控指南",
        doc_name="risk_guide.pdf",
        source_type=SourceType.PDF,
        source_uri="knowledge/risk/risk_guide.pdf",
        current_version_id=None,
        status=DocumentStatus.INACTIVE,
        permission_scope=PermissionScope.INTERNAL,
    )

    assert document.current_version_id is None


def test_document_extra_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        KnowledgeDocument(
            doc_id="risk_guide",
            kb_id=DEFAULT_RISK_KB_ID,
            doc_title="智能风控指南",
            doc_name="risk_guide.pdf",
            source_type=SourceType.PDF,
            source_uri="knowledge/risk/risk_guide.pdf",
            status=DocumentStatus.INACTIVE,
            permission_scope=PermissionScope.INTERNAL,
            unexpected_field="boom",
        )


def test_version_and_job_require_core_fields() -> None:
    version = KnowledgeDocumentVersion(
        version_id="risk_guide_202606",
        doc_id="risk_guide",
        kb_id=DEFAULT_RISK_KB_ID,
        version="2026-06",
        file_hash="sha256:test",
        file_uri="knowledge/risk/risk_guide.pdf",
        parser_version="swxy_deepdoc_v1",
        chunker_version="m2d_chunker_v1",
        embedding_model="text-embedding-v3",
        embedding_dim=1024,
        index_name="chord_m2d_risk_knowledge_v1",
        status=DocumentVersionStatus.UPLOADED,
    )
    job = KnowledgeIngestJob(
        job_id="job_1",
        kb_id=DEFAULT_RISK_KB_ID,
        doc_id="risk_guide",
        version_id="risk_guide_202606",
        status=IngestJobStatus.UPLOADED,
        current_step=IngestStep.UPLOADED,
        error_message=None,
    )

    assert version.status == DocumentVersionStatus.UPLOADED
    assert job.current_step == IngestStep.UPLOADED


def test_chunk_schema_can_be_created_without_repository() -> None:
    chunk = KnowledgeChunk(
        chunk_id="risk_guide_202606_chunk_000001",
        kb_id=DEFAULT_RISK_KB_ID,
        doc_id="risk_guide",
        version_id="risk_guide_202606",
        chunk_order=1,
        chunk_type="paragraph",
        section_title="贷后风险识别",
        section_path=["智能风控指南", "贷后管理", "贷后风险识别"],
        page_start=12,
        page_end=13,
        content="text",
        content_hash="sha256:chunk",
        status=ChunkStatus.INDEXED,
        permission_scope=PermissionScope.INTERNAL,
    )

    assert chunk.status == ChunkStatus.INDEXED
    assert chunk.permission_scope == PermissionScope.INTERNAL


def test_invalid_enum_values_fail() -> None:
    with pytest.raises(ValidationError):
        KnowledgeDocument(
            doc_id="risk_guide",
            kb_id=DEFAULT_RISK_KB_ID,
            doc_title="智能风控指南",
            doc_name="risk_guide.pdf",
            source_type="csv",
            source_uri="knowledge/risk/risk_guide.pdf",
            status=DocumentStatus.INACTIVE,
            permission_scope=PermissionScope.INTERNAL,
        )


def test_chunk_order_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        KnowledgeChunk(
            chunk_id="risk_guide_202606_chunk_000000",
            kb_id=DEFAULT_RISK_KB_ID,
            doc_id="risk_guide",
            version_id="risk_guide_202606",
            chunk_order=0,
            chunk_type="paragraph",
            section_title="贷后风险识别",
            section_path=["智能风控指南"],
            page_start=12,
            page_end=13,
            content="text",
            content_hash="sha256:chunk",
            status=ChunkStatus.INDEXED,
        )


def test_chunk_page_range_must_be_valid() -> None:
    with pytest.raises(ValidationError):
        KnowledgeChunk(
            chunk_id="risk_guide_202606_chunk_000001",
            kb_id=DEFAULT_RISK_KB_ID,
            doc_id="risk_guide",
            version_id="risk_guide_202606",
            chunk_order=1,
            chunk_type="paragraph",
            section_title="贷后风险识别",
            section_path=["智能风控指南"],
            page_start=14,
            page_end=13,
            content="text",
            content_hash="sha256:chunk",
            status=ChunkStatus.INDEXED,
        )
