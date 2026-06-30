from __future__ import annotations

import pytest

from app.knowledge_base.schemas import (
    ChunkStatus,
    DocumentVersionStatus,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    PermissionScope,
    SourceType,
)
from app.risk_knowledge.ingestion.schemas import ParsedDocument, RawParsedChunk, SourceDocumentRef
from app.risk_knowledge.metadata.chunk_builder import KnowledgeChunkBuilder
from app.risk_knowledge.metadata.content_hash import build_content_hash
from app.risk_knowledge.metadata.errors import MetadataInputMismatchError


def _build_parsed_document() -> ParsedDocument:
    return ParsedDocument(
        source=SourceDocumentRef(
            kb_id="risk_domain_knowledge",
            doc_id="risk_guide",
            version_id="risk_guide_202607",
            file_path="/tmp/risk_guide.pdf",
            doc_name="risk_guide.pdf",
            source_type=SourceType.PDF,
        ),
        parser_name="swxy",
        parser_version="swxy-parser-v1",
        document_metadata={"language": "zh"},
        raw_chunks=[
            RawParsedChunk(
                chunk_order=1,
                raw_content=" 贷后风险识别是指...\r\n ",
                chunk_type=None,
                title="通用标题",
                section_title=None,
                section_path=["智能风控指南", "贷后管理"],
                page_start=12,
                page_end=12,
                position={"position_int": 3},
                source_metadata={"raw_chunk_type": "raw_paragraph"},
            )
        ],
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
        status="active",
        permission_scope=PermissionScope.RESTRICTED,
    )


def _build_version(*, status: DocumentVersionStatus = DocumentVersionStatus.PARSED) -> KnowledgeDocumentVersion:
    return KnowledgeDocumentVersion(
        version_id="risk_guide_202607",
        doc_id="risk_guide",
        kb_id="risk_domain_knowledge",
        version="2026-07",
        file_hash="sha256:test",
        file_uri="knowledge/risk/risk_guide.pdf",
        parser_version="version-parser-v0",
        chunker_version="chunker-v1",
        embedding_model=None,
        embedding_dim=None,
        index_name=None,
        status=status,
    )


def test_chunk_builder_materializes_stable_knowledge_chunk() -> None:
    builder = KnowledgeChunkBuilder()

    result = builder.build(_build_parsed_document(), _build_document(), _build_version())

    chunk = result.chunks[0]
    assert chunk.chunk_id == "risk_guide_202607_chunk_000001"
    assert chunk.status == ChunkStatus.PENDING
    assert chunk.permission_scope == PermissionScope.RESTRICTED
    assert chunk.source_type == SourceType.PDF
    assert chunk.source_uri == "knowledge/risk/risk_guide.pdf"
    assert chunk.section_title == "贷后管理"
    assert chunk.chunk_type == "paragraph"
    assert chunk.content == " 贷后风险识别是指...\r\n "
    assert chunk.content_hash == build_content_hash(" 贷后风险识别是指...\r\n ")
    assert chunk.parser_version == "swxy-parser-v1"
    assert chunk.chunker_version == "chunker-v1"
    assert chunk.embedding_model is None
    assert chunk.embedding_dim is None
    assert chunk.es_index_name is None
    assert chunk.es_doc_id is None
    assert chunk.source_metadata == {
        "file_path": "/tmp/risk_guide.pdf",
        "doc_name": "risk_guide.pdf",
        "document_metadata": {"language": "zh"},
        "chunk_metadata": {"raw_chunk_type": "raw_paragraph"},
        "position": {"position_int": 3},
    }


def test_chunk_builder_requires_parsed_version_status() -> None:
    builder = KnowledgeChunkBuilder()

    with pytest.raises(MetadataInputMismatchError):
        builder.build(_build_parsed_document(), _build_document(), _build_version(status=DocumentVersionStatus.UPLOADED))


def test_chunk_builder_rejects_mismatched_identity() -> None:
    builder = KnowledgeChunkBuilder()
    document = _build_document().model_copy(update={"doc_id": "other_doc"})

    with pytest.raises(MetadataInputMismatchError):
        builder.build(_build_parsed_document(), document, _build_version())
