from __future__ import annotations

import pytest

from app.knowledge_base.schemas import (
    ChunkStatus,
    DocumentStatus,
    DocumentVersionStatus,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    PermissionScope,
    SourceType,
)
from app.risk_knowledge.metadata.errors import EmptyMetadataBuildInputError, MetadataInputMismatchError
from app.risk_knowledge.metadata.evidence_builder import RiskEvidenceBuilder
from app.risk_knowledge.schemas import EvidenceUsage


def _build_chunk() -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id="risk_guide_202607_chunk_000001",
        kb_id="risk_domain_knowledge",
        doc_id="risk_guide",
        version_id="risk_guide_202607",
        chunk_order=1,
        chunk_type="paragraph",
        section_title="贷后风险识别",
        section_path=["智能风控指南", "贷后风险识别"],
        page_start=12,
        page_end=12,
        content="贷后风险识别是指...",
        content_hash="sha256:test",
        status=ChunkStatus.PENDING,
        permission_scope=PermissionScope.INTERNAL,
        source_type=SourceType.PDF,
        source_uri="knowledge/risk/risk_guide.pdf",
        source_metadata={"doc_name": "risk_guide.pdf"},
    )


def _build_document() -> KnowledgeDocument:
    return KnowledgeDocument(
        doc_id="risk_guide",
        kb_id="risk_domain_knowledge",
        doc_title="智能风控指南",
        doc_name="risk_guide.pdf",
        source_type=SourceType.PDF,
        source_uri="knowledge/risk/risk_guide.pdf",
        current_version_id="risk_guide_202607",
        status=DocumentStatus.ACTIVE,
        permission_scope=PermissionScope.INTERNAL,
    )


def _build_version() -> KnowledgeDocumentVersion:
    return KnowledgeDocumentVersion(
        version_id="risk_guide_202607",
        doc_id="risk_guide",
        kb_id="risk_domain_knowledge",
        version="2026-07",
        file_hash="sha256:test",
        file_uri="knowledge/risk/risk_guide.pdf",
        parser_version="swxy-parser-v1",
        chunker_version="chunker-v1",
        embedding_model=None,
        embedding_dim=None,
        index_name=None,
        status=DocumentVersionStatus.PARSED,
    )


def test_evidence_builder_materializes_draft_evidence() -> None:
    builder = RiskEvidenceBuilder()

    result = builder.build([_build_chunk()], _build_document(), _build_version())

    evidence = result.evidence[0]
    assert evidence.evidence_id == "ev_risk_guide_202607_chunk_000001"
    assert evidence.section_title == "贷后风险识别"
    assert evidence.page_start == 12
    assert evidence.page_end == 12
    assert evidence.text == "贷后风险识别是指..."
    assert evidence.score is None
    assert evidence.usage == EvidenceUsage.SUPPORTING_EVIDENCE


def test_evidence_builder_rejects_empty_chunks() -> None:
    builder = RiskEvidenceBuilder()

    with pytest.raises(EmptyMetadataBuildInputError):
        builder.build([], _build_document(), _build_version())


def test_evidence_builder_rejects_mismatched_identity() -> None:
    builder = RiskEvidenceBuilder()
    mismatched_chunk = _build_chunk().model_copy(update={"version_id": "other_version"})

    with pytest.raises(MetadataInputMismatchError):
        builder.build([mismatched_chunk], _build_document(), _build_version())
