"""Chunk persistence service for M2D-8."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.knowledge_base.schemas import KnowledgeChunk, KnowledgeDocumentVersion
from app.risk_knowledge.metadata.content_hash import build_content_hash
from app.risk_knowledge.persistence.errors import ChunkContentConflictError
from app.risk_knowledge.persistence.models import KnowledgeChunkRecord
from app.risk_knowledge.persistence.repositories import (
    SqlAlchemyKnowledgeChunkRepository,
    to_persisted_chunk_record,
)
from app.risk_knowledge.persistence.schemas import PersistedChunkBatchResult


class KnowledgeChunkPersistenceService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._repository = SqlAlchemyKnowledgeChunkRepository(db)

    def persist_chunks(
        self,
        version: KnowledgeDocumentVersion,
        chunks: list[KnowledgeChunk],
    ) -> PersistedChunkBatchResult:
        records = []
        for chunk in chunks:
            self._validate_chunk(version, chunk)
            existing = self._repository.get_by_version_and_chunk(version.version_id, chunk.chunk_id)
            if existing is not None:
                if existing.content_hash != chunk.content_hash:
                    raise ChunkContentConflictError(
                        f"chunk content conflict for version_id={version.version_id} chunk_id={chunk.chunk_id}"
                    )
                records.append(to_persisted_chunk_record(existing))
                continue

            created = self._repository.create(
                KnowledgeChunkRecord(
                    kb_id=chunk.kb_id,
                    doc_id=chunk.doc_id,
                    version_id=chunk.version_id,
                    chunk_id=chunk.chunk_id,
                    chunk_order=chunk.chunk_order,
                    chunk_type=chunk.chunk_type,
                    section_title=chunk.section_title,
                    section_path_json=list(chunk.section_path),
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    content_text=chunk.content,
                    content_hash=chunk.content_hash,
                    normalized_content_hash=build_content_hash(chunk.content),
                    permission_scope=chunk.permission_scope.value,
                    source_type=chunk.source_type.value if chunk.source_type is not None else None,
                    source_uri=chunk.source_uri,
                    token_count=None,
                    metadata_json={
                        "source_metadata": dict(chunk.source_metadata),
                        "parser_version": chunk.parser_version,
                        "chunker_version": chunk.chunker_version,
                    },
                )
            )
            records.append(to_persisted_chunk_record(created))

        self._db.commit()
        return PersistedChunkBatchResult(records=records)

    def _validate_chunk(self, version: KnowledgeDocumentVersion, chunk: KnowledgeChunk) -> None:
        if chunk.version_id != version.version_id:
            raise ValueError(f"chunk.version_id mismatch for chunk_id={chunk.chunk_id}")
        if chunk.doc_id != version.doc_id:
            raise ValueError(f"chunk.doc_id mismatch for chunk_id={chunk.chunk_id}")
        if chunk.kb_id != version.kb_id:
            raise ValueError(f"chunk.kb_id mismatch for chunk_id={chunk.chunk_id}")
