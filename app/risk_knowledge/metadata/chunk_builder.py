"""Pure builder that materializes `KnowledgeChunk` contracts from parsed input."""

from __future__ import annotations

from app.knowledge_base.id_factory import build_chunk_id
from app.knowledge_base.schemas import (
    ChunkStatus,
    DocumentVersionStatus,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
)
from app.risk_knowledge.ingestion.schemas import ParsedDocument, RawParsedChunk
from app.risk_knowledge.metadata.content_hash import build_content_hash
from app.risk_knowledge.metadata.errors import EmptyMetadataBuildInputError, MetadataInputMismatchError
from app.risk_knowledge.schemas import MetadataBuildResult


class KnowledgeChunkBuilder:
    def build(
        self,
        parsed_document: ParsedDocument,
        document: KnowledgeDocument,
        version: KnowledgeDocumentVersion,
    ) -> MetadataBuildResult:
        self._validate_inputs(parsed_document, document, version)
        chunks = [
            self._build_chunk(raw_chunk, parsed_document, document, version)
            for raw_chunk in parsed_document.raw_chunks
        ]
        return MetadataBuildResult(chunks=chunks)

    def _validate_inputs(
        self,
        parsed_document: ParsedDocument,
        document: KnowledgeDocument,
        version: KnowledgeDocumentVersion,
    ) -> None:
        if not parsed_document.raw_chunks:
            raise EmptyMetadataBuildInputError("parsed_document.raw_chunks must not be empty")
        if not document.doc_title.strip():
            raise MetadataInputMismatchError("document.doc_title must not be empty")
        if version.status != DocumentVersionStatus.PARSED:
            raise MetadataInputMismatchError("M2D-7 requires version.status == parsed")
        if parsed_document.source.kb_id != document.kb_id or document.kb_id != version.kb_id:
            raise MetadataInputMismatchError("kb_id mismatch between parsed_document, document, and version")
        if parsed_document.source.doc_id != document.doc_id or document.doc_id != version.doc_id:
            raise MetadataInputMismatchError("doc_id mismatch between parsed_document, document, and version")
        if parsed_document.source.version_id != version.version_id:
            raise MetadataInputMismatchError("version_id mismatch between parsed_document and version")

    def _build_chunk(
        self,
        raw_chunk: RawParsedChunk,
        parsed_document: ParsedDocument,
        document: KnowledgeDocument,
        version: KnowledgeDocumentVersion,
    ) -> KnowledgeChunk:
        section_title = raw_chunk.section_title or self._last_section_path(raw_chunk) or raw_chunk.title
        return KnowledgeChunk(
            chunk_id=build_chunk_id(version.version_id, raw_chunk.chunk_order),
            kb_id=document.kb_id,
            doc_id=document.doc_id,
            version_id=version.version_id,
            chunk_order=raw_chunk.chunk_order,
            chunk_type=raw_chunk.chunk_type or "paragraph",
            section_title=section_title,
            section_path=list(raw_chunk.section_path),
            page_start=raw_chunk.page_start,
            page_end=raw_chunk.page_end,
            content=raw_chunk.raw_content,
            content_hash=build_content_hash(raw_chunk.raw_content),
            status=ChunkStatus.PENDING,
            es_index_name=None,
            es_doc_id=None,
            embedding_model=None,
            embedding_dim=None,
            parser_version=parsed_document.parser_version or version.parser_version,
            chunker_version=version.chunker_version,
            permission_scope=document.permission_scope,
            source_type=document.source_type,
            source_uri=document.source_uri,
            source_metadata={
                "file_path": parsed_document.source.file_path,
                "doc_name": parsed_document.source.doc_name,
                "document_metadata": dict(parsed_document.document_metadata),
                "chunk_metadata": dict(raw_chunk.source_metadata),
                "position": dict(raw_chunk.position or {}),
            },
        )

    @staticmethod
    def _last_section_path(raw_chunk: RawParsedChunk) -> str | None:
        return raw_chunk.section_path[-1] if raw_chunk.section_path else None
