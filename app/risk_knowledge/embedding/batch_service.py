"""Embedding batch service for persisted M2D-8 chunk records."""

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from app.risk_knowledge.embedding.base import EmbeddingProvider
from app.risk_knowledge.embedding.errors import (
    EmbeddingDimensionMismatchError,
    EmbeddingInputError,
    EmbeddingProviderError,
)
from app.risk_knowledge.embedding.schemas import EmbeddingInput
from app.risk_knowledge.persistence.repositories import (
    SqlAlchemyKnowledgeChunkEmbeddingRepository,
    SqlAlchemyKnowledgeChunkRepository,
    to_persisted_embedding_record,
)
from app.risk_knowledge.persistence.schemas import PersistedEmbeddingBatchResult


class EmbeddingBatchService:
    def __init__(
        self,
        *,
        provider: EmbeddingProvider,
        expected_dimension: int,
        db: Session | None = None,
    ) -> None:
        self._provider = provider
        self._expected_dimension = expected_dimension
        self._db = db

    def embed_inputs(self, inputs: list[EmbeddingInput]) -> PersistedEmbeddingBatchResult:
        if not inputs:
            raise EmbeddingInputError("embedding inputs must not be empty")
        records = self._embed_records(inputs)
        return PersistedEmbeddingBatchResult(
            records=[
                {
                    "embedding_id": self._build_embedding_id(record),
                    "chunk_id": record.chunk_id,
                    "version_id": "",
                    "content_hash": record.content_hash,
                    "provider": record.provider,
                    "model": record.model,
                    "dimension": record.dimension,
                    "vector_checksum": record.vector_checksum,
                    "status": "ready",
                }
                for record in records
            ]
        )

    def embed_persisted_chunks(self, *, version_id: str, chunk_ids: list[str]) -> PersistedEmbeddingBatchResult:
        if self._db is None:
            raise ValueError("db session is required for embed_persisted_chunks")
        chunk_repo = SqlAlchemyKnowledgeChunkRepository(self._db)
        embedding_repo = SqlAlchemyKnowledgeChunkEmbeddingRepository(self._db)
        chunk_records = chunk_repo.list_by_version_and_chunk_ids(version_id, chunk_ids)
        if not chunk_records:
            raise EmbeddingInputError(f"no persisted chunks found for version_id={version_id}")
        embedded = self._embed_records(
            [
                EmbeddingInput(
                    chunk_id=record.chunk_id,
                    content_hash=record.content_hash,
                    text=record.content_text,
                    input_type="document",
                )
                for record in chunk_records
            ]
        )
        persisted_records = []
        chunks_by_id = {record.chunk_id: record for record in chunk_records}
        for record in embedded:
            parent = chunks_by_id[record.chunk_id]
            persisted = embedding_repo.create_or_validate_idempotent(
                kb_id=parent.kb_id,
                doc_id=parent.doc_id,
                version_id=parent.version_id,
                result=record,
                embedding_id=self._build_embedding_id(record),
            )
            persisted_records.append(to_persisted_embedding_record(persisted))
        self._db.commit()
        return PersistedEmbeddingBatchResult(records=persisted_records)

    def _embed_records(self, inputs: list[EmbeddingInput]):
        max_batch_size = getattr(self._provider, "max_batch_size", None)
        if max_batch_size is None or max_batch_size <= 0:
            records = self._provider.embed(inputs)
            self._validate_batch_result(inputs, records)
            return records

        all_records = []
        for start in range(0, len(inputs), max_batch_size):
            batch_inputs = inputs[start : start + max_batch_size]
            batch_records = self._provider.embed(batch_inputs)
            self._validate_batch_result(batch_inputs, batch_records)
            all_records.extend(batch_records)
        return all_records

    def _validate_batch_result(self, inputs: list[EmbeddingInput], records) -> None:
        if len(records) != len(inputs):
            raise EmbeddingProviderError("embedding provider returned mismatched record count")
        for record in records:
            if record.dimension != self._expected_dimension:
                raise EmbeddingDimensionMismatchError(
                    f"expected dimension {self._expected_dimension}, got {record.dimension}"
                )

    def _build_embedding_id(self, record) -> str:
        checksum = hashlib.sha256(
            f"{record.chunk_id}|{record.provider}|{record.model}|{record.dimension}|{record.content_hash}".encode("utf-8")
        ).hexdigest()[:12]
        return f"emb_{record.chunk_id}_{checksum}"
