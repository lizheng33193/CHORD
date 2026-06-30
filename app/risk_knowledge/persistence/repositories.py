"""SQLAlchemy repositories for M2D-8 persistence artifacts."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.risk_knowledge.embedding.schemas import EmbeddingVectorResult
from app.risk_knowledge.indexing.schemas import FaissIndexManifest, FaissVectorMappingEntry
from app.risk_knowledge.persistence.errors import ChunkContentConflictError, EmbeddingMetadataConflictError
from app.risk_knowledge.persistence.models import (
    FaissIndexManifestRecord,
    FaissVectorMappingRecord,
    KnowledgeChunkEmbeddingRecord,
    KnowledgeChunkRecord,
)
from app.risk_knowledge.persistence.schemas import (
    PersistedChunkRecord,
    PersistedEmbeddingRecord,
)


class SqlAlchemyKnowledgeChunkRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_version_and_chunk(self, version_id: str, chunk_id: str) -> KnowledgeChunkRecord | None:
        return self._db.scalar(
            select(KnowledgeChunkRecord).where(
                KnowledgeChunkRecord.version_id == version_id,
                KnowledgeChunkRecord.chunk_id == chunk_id,
            )
        )

    def list_by_version_and_chunk_ids(self, version_id: str, chunk_ids: list[str]) -> list[KnowledgeChunkRecord]:
        stmt = select(KnowledgeChunkRecord).where(KnowledgeChunkRecord.version_id == version_id)
        if chunk_ids:
            stmt = stmt.where(KnowledgeChunkRecord.chunk_id.in_(chunk_ids))
        stmt = stmt.order_by(KnowledgeChunkRecord.chunk_id.asc())
        return list(self._db.scalars(stmt).all())

    def list_by_version(self, version_id: str) -> list[KnowledgeChunkRecord]:
        return self.list_by_version_and_chunk_ids(version_id, [])

    def create(self, record: KnowledgeChunkRecord) -> KnowledgeChunkRecord:
        self._db.add(record)
        self._db.flush()
        self._db.refresh(record)
        return record


class SqlAlchemyKnowledgeChunkEmbeddingRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_existing(
        self,
        *,
        version_id: str,
        chunk_id: str,
        provider: str,
        model: str,
        dimension: int,
    ) -> KnowledgeChunkEmbeddingRecord | None:
        return self._db.scalar(
            select(KnowledgeChunkEmbeddingRecord).where(
                KnowledgeChunkEmbeddingRecord.version_id == version_id,
                KnowledgeChunkEmbeddingRecord.chunk_id == chunk_id,
                KnowledgeChunkEmbeddingRecord.provider == provider,
                KnowledgeChunkEmbeddingRecord.model == model,
                KnowledgeChunkEmbeddingRecord.dimension == dimension,
            )
        )

    def create_or_validate_idempotent(
        self,
        *,
        kb_id: str,
        doc_id: str,
        version_id: str,
        result: EmbeddingVectorResult,
        embedding_id: str,
    ) -> KnowledgeChunkEmbeddingRecord:
        existing = self.get_existing(
            version_id=version_id,
            chunk_id=result.chunk_id,
            provider=result.provider,
            model=result.model,
            dimension=result.dimension,
        )
        if existing is not None:
            if existing.content_hash != result.content_hash:
                raise EmbeddingMetadataConflictError(
                    f"existing embedding content hash mismatch for chunk_id={result.chunk_id}"
                )
            if existing.vector_checksum != result.vector_checksum:
                raise EmbeddingMetadataConflictError(
                    f"existing embedding checksum mismatch for chunk_id={result.chunk_id}"
                )
            return existing

        record = KnowledgeChunkEmbeddingRecord(
            embedding_id=embedding_id,
            kb_id=kb_id,
            doc_id=doc_id,
            version_id=version_id,
            chunk_id=result.chunk_id,
            content_hash=result.content_hash,
            provider=result.provider,
            model=result.model,
            dimension=result.dimension,
            vector_json=list(result.vector),
            vector_checksum=result.vector_checksum,
            status="ready",
        )
        self._db.add(record)
        self._db.flush()
        self._db.refresh(record)
        return record

    def list_by_version(self, version_id: str) -> list[KnowledgeChunkEmbeddingRecord]:
        return list(
            self._db.scalars(
                select(KnowledgeChunkEmbeddingRecord)
                .where(KnowledgeChunkEmbeddingRecord.version_id == version_id)
                .order_by(KnowledgeChunkEmbeddingRecord.chunk_id.asc())
            ).all()
        )


class SqlAlchemyFaissIndexRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def save_manifest(self, manifest: FaissIndexManifest) -> FaissIndexManifestRecord:
        existing = self._db.scalar(
            select(FaissIndexManifestRecord).where(FaissIndexManifestRecord.index_id == manifest.index_id)
        )
        if existing is None:
            existing = FaissIndexManifestRecord(index_id=manifest.index_id)
            self._db.add(existing)

        existing.kb_id = manifest.kb_id
        existing.version_id = manifest.version_id
        existing.embedding_provider = manifest.embedding_provider
        existing.embedding_model = manifest.embedding_model
        existing.embedding_dimension = manifest.embedding_dimension
        existing.job_id = manifest.job_id
        existing.index_type = manifest.index_type
        existing.distance_metric = manifest.distance_metric
        existing.record_count = manifest.record_count
        existing.artifact_path = manifest.artifact_path
        existing.mapping_path = manifest.mapping_path
        existing.checksum = manifest.checksum
        existing.build_fingerprint = manifest.build_fingerprint
        existing.build_status = manifest.build_status
        existing.is_active = manifest.is_active
        existing.superseded_by_index_id = manifest.superseded_by_index_id
        existing.superseded_at = manifest.superseded_at
        existing.built_at = manifest.built_at
        self._db.flush()
        self._db.refresh(existing)
        return existing

    def get(self, index_id: str) -> FaissIndexManifestRecord | None:
        return self._db.scalar(
            select(FaissIndexManifestRecord).where(FaissIndexManifestRecord.index_id == index_id)
        )

    def get_active_by_version(self, version_id: str) -> FaissIndexManifestRecord | None:
        return self._db.scalar(
            select(FaissIndexManifestRecord).where(
                FaissIndexManifestRecord.version_id == version_id,
                FaissIndexManifestRecord.is_active.is_(True),
            )
        )

    def get_by_version_and_fingerprint(self, version_id: str, fingerprint: str) -> FaissIndexManifestRecord | None:
        return self._db.scalar(
            select(FaissIndexManifestRecord).where(
                FaissIndexManifestRecord.version_id == version_id,
                FaissIndexManifestRecord.build_fingerprint == fingerprint,
            )
        )

    def activate_manifest(self, *, version_id: str, index_id: str) -> FaissIndexManifestRecord:
        now = datetime.now(UTC).replace(tzinfo=None)
        current = self.get_active_by_version(version_id)
        if current is not None and current.index_id != index_id:
            current.is_active = False
            current.superseded_by_index_id = index_id
            current.superseded_at = now
            current.build_status = "superseded"

        target = self.get(index_id)
        if target is None:
            raise ValueError(f"manifest not found: {index_id}")
        target.is_active = True
        target.superseded_by_index_id = None
        target.superseded_at = None
        target.build_status = "active"
        self._db.flush()
        self._db.refresh(target)
        return target

    def replace_vector_mappings(
        self,
        *,
        index_id: str,
        mappings: dict[int, FaissVectorMappingEntry],
    ) -> None:
        self._db.execute(delete(FaissVectorMappingRecord).where(FaissVectorMappingRecord.index_id == index_id))
        for vector_id, entry in mappings.items():
            self._db.add(
                FaissVectorMappingRecord(
                    index_id=index_id,
                    vector_id=int(vector_id),
                    chunk_id=entry.chunk_id,
                    embedding_id=entry.embedding_id,
                    content_hash=entry.content_hash,
                )
            )
        self._db.flush()


def to_persisted_chunk_record(record: KnowledgeChunkRecord) -> PersistedChunkRecord:
    return PersistedChunkRecord(
        id=record.id,
        kb_id=record.kb_id,
        doc_id=record.doc_id,
        version_id=record.version_id,
        chunk_id=record.chunk_id,
        content_hash=record.content_hash,
        normalized_content_hash=record.normalized_content_hash,
        metadata_json=dict(record.metadata_json or {}),
        token_count=record.token_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def to_persisted_embedding_record(record: KnowledgeChunkEmbeddingRecord) -> PersistedEmbeddingRecord:
    return PersistedEmbeddingRecord(
        id=record.id,
        embedding_id=record.embedding_id,
        chunk_id=record.chunk_id,
        version_id=record.version_id,
        content_hash=record.content_hash,
        provider=record.provider,
        model=record.model,
        dimension=record.dimension,
        vector_checksum=record.vector_checksum,
        status=record.status,
    )


def to_manifest_schema(record: FaissIndexManifestRecord) -> FaissIndexManifest:
    return FaissIndexManifest.model_validate(
        {
            "index_id": record.index_id,
            "kb_id": record.kb_id,
            "version_id": record.version_id,
            "embedding_provider": record.embedding_provider,
            "embedding_model": record.embedding_model,
            "embedding_dimension": record.embedding_dimension,
            "job_id": record.job_id,
            "index_type": record.index_type,
            "distance_metric": record.distance_metric,
            "record_count": record.record_count,
            "artifact_path": record.artifact_path,
            "mapping_path": record.mapping_path,
            "checksum": record.checksum,
            "build_fingerprint": record.build_fingerprint,
            "build_status": record.build_status,
            "is_active": record.is_active,
            "superseded_by_index_id": record.superseded_by_index_id,
            "superseded_at": record.superseded_at,
            "built_at": record.built_at,
        }
    )
