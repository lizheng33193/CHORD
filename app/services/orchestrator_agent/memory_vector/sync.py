"""Sync service for M6A memory vector shadow indexing."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.services.orchestrator_agent.memory_store import SQLiteMemoryStore, now_iso

from .embedding_text import build_memory_embedding_text
from .faiss_store import MemoryFaissStore
from .provider import MemoryEmbeddingProvider, build_memory_embedding_provider
from .schemas import (
    MemoryVectorManifest,
    MemoryVectorMetadata,
    MemoryVectorRecord,
    MemoryVectorSyncReport,
    MemoryVectorSyncResult,
    MemoryVectorSyncState,
)


@dataclass
class MemoryVectorSyncService:
    relational_store: SQLiteMemoryStore
    vector_store: MemoryFaissStore
    embedding_provider: MemoryEmbeddingProvider

    def sync_memory(self, memory_id: str) -> MemoryVectorSyncResult:
        memory = self.relational_store.get_record_by_id(memory_id)
        existing = self.get_sync_status(memory_id)
        if memory is None:
            state = self._build_state(
                memory_id=memory_id,
                content_hash=(existing.content_hash if existing else _sha256_text("")),
                embedding_text_hash=(existing.embedding_text_hash if existing else None),
                vector_status="deleted",
                indexed_at=(existing.indexed_at if existing else None),
                last_error=None,
                created_at=(existing.created_at if existing else now_iso()),
            )
            self.relational_store.upsert_vector_sync_state(state)
            self.vector_store.delete([memory_id])
            self.vector_store.persist()
            return MemoryVectorSyncResult(memory_id=memory_id, status="deleted", reason="memory_missing")

        if str(memory.get("status") or "").strip().lower() != "active":
            state = self._build_state(
                memory_id=memory_id,
                content_hash=_sha256_text(str(memory.get("content") or "")),
                embedding_text_hash=(existing.embedding_text_hash if existing else None),
                vector_status="deleted",
                indexed_at=(existing.indexed_at if existing else None),
                last_error=None,
                created_at=(existing.created_at if existing else now_iso()),
            )
            self.relational_store.upsert_vector_sync_state(state)
            self.vector_store.delete([memory_id])
            self.vector_store.persist()
            return MemoryVectorSyncResult(memory_id=memory_id, status="deleted", reason="inactive_memory")

        text_result = build_memory_embedding_text(memory, max_chars=settings.memory_vector_text_max_chars)
        if text_result.skipped:
            state = self._build_state(
                memory_id=memory_id,
                content_hash=text_result.content_hash or _sha256_text(""),
                embedding_text_hash=text_result.embedding_text_hash,
                vector_status="skipped",
                indexed_at=(existing.indexed_at if existing else None),
                last_error=None,
                created_at=(existing.created_at if existing else now_iso()),
            )
            self.relational_store.upsert_vector_sync_state(state)
            return MemoryVectorSyncResult(memory_id=memory_id, status="skipped", reason=text_result.reason)

        try:
            vectors = self.embedding_provider.embed_texts([text_result.text], input_type="document")
            vector = list(vectors[0])
            metadata = MemoryVectorMetadata(
                memory_id=str(memory["memory_id"]),
                user_id=str(memory.get("user_id") or "") or None,
                project_id=str(memory.get("project_id") or "") or None,
                country=str(memory.get("country") or "") or None,
                category=str(memory.get("category") or "") or None,
                memory_type=str(memory.get("memory_type") or "") or None,
                source=str(memory.get("source") or "") or None,
                status=str(memory.get("status") or "") or None,
                importance=float(memory.get("importance") or 0.0),
                confidence=float(memory.get("confidence") or 0.0),
                created_at=str(memory.get("created_at") or "") or None,
                updated_at=str(memory.get("updated_at") or "") or None,
                content_hash=text_result.content_hash or _sha256_text(str(memory.get("content") or "")),
                embedding_provider=self.embedding_provider.provider_name,
                embedding_model=self.embedding_provider.model_name,
                embedding_dim=self.embedding_provider.dimension,
                vector_status="indexed",
                is_current=True,
                metadata=dict(memory.get("metadata") or {}),
            )
            record = MemoryVectorRecord(
                memory_id=str(memory["memory_id"]),
                embedding_text=text_result.text,
                embedding_text_hash=text_result.embedding_text_hash or _sha256_text(text_result.text),
                content_hash=text_result.content_hash or _sha256_text(str(memory.get("content") or "")),
                embedding=vector,
                metadata=metadata,
            )
            self.vector_store.upsert([record])
            self.vector_store.persist()
            state = self._build_state(
                memory_id=memory_id,
                content_hash=record.content_hash,
                embedding_text_hash=record.embedding_text_hash,
                vector_status="indexed",
                indexed_at=now_iso(),
                last_error=None,
                created_at=(existing.created_at if existing else now_iso()),
            )
            self.relational_store.upsert_vector_sync_state(state)
            return MemoryVectorSyncResult(memory_id=memory_id, status="indexed")
        except Exception as exc:  # pragma: no cover - covered by failing-provider test
            state = self._build_state(
                memory_id=memory_id,
                content_hash=text_result.content_hash or _sha256_text(str(memory.get("content") or "")),
                embedding_text_hash=text_result.embedding_text_hash,
                vector_status="failed",
                indexed_at=(existing.indexed_at if existing else None),
                last_error=str(exc),
                created_at=(existing.created_at if existing else now_iso()),
            )
            self.relational_store.upsert_vector_sync_state(state)
            return MemoryVectorSyncResult(memory_id=memory_id, status="failed", error=str(exc))

    def sync_all_active(
        self,
        *,
        user_id: str | None = None,
        project_id: str | None = None,
        country: str | None = None,
        limit: int | None = None,
    ) -> MemoryVectorSyncReport:
        rows = self.relational_store.list_records(
            user_id=user_id,
            project_id=project_id,
            country=country,
            status="active",
            limit=limit or 1000,
        )
        results = [self.sync_memory(str(row["memory_id"])) for row in rows]
        return _build_report(results)

    def mark_deleted(self, memory_id: str) -> None:
        existing = self.get_sync_status(memory_id)
        state = self._build_state(
            memory_id=memory_id,
            content_hash=(existing.content_hash if existing else _sha256_text("")),
            embedding_text_hash=(existing.embedding_text_hash if existing else None),
            vector_status="deleted",
            indexed_at=(existing.indexed_at if existing else None),
            last_error=None,
            created_at=(existing.created_at if existing else now_iso()),
        )
        self.relational_store.upsert_vector_sync_state(state)
        self.vector_store.delete([memory_id])
        self.vector_store.persist()

    def rebuild_index(self, filters: dict | None = None) -> MemoryVectorSyncReport:
        filters = dict(filters or {})
        rows = self.relational_store.list_records(
            user_id=filters.get("user_id"),
            project_id=filters.get("project_id"),
            country=filters.get("country"),
            status="active",
            limit=filters.get("limit") or 5000,
        )
        texts: list[str] = []
        memory_rows: list[dict] = []
        skipped: list[MemoryVectorSyncResult] = []
        for row in rows:
            text_result = build_memory_embedding_text(row, max_chars=settings.memory_vector_text_max_chars)
            if text_result.skipped:
                skipped.append(
                    MemoryVectorSyncResult(
                        memory_id=str(row["memory_id"]),
                        status="skipped",
                        reason=text_result.reason,
                    )
                )
                self.relational_store.upsert_vector_sync_state(
                    self._build_state(
                        memory_id=str(row["memory_id"]),
                        content_hash=text_result.content_hash or _sha256_text(str(row.get("content") or "")),
                        embedding_text_hash=text_result.embedding_text_hash,
                        vector_status="skipped",
                        indexed_at=None,
                        last_error=None,
                        created_at=(self.get_sync_status(str(row["memory_id"])).created_at if self.get_sync_status(str(row["memory_id"])) else now_iso()),
                    )
                )
                continue
            texts.append(text_result.text)
            row["_embedding_text_result"] = text_result
            memory_rows.append(row)

        vectors = self.embedding_provider.embed_texts(texts, input_type="document") if texts else []
        records: list[MemoryVectorRecord] = []
        for row, vector in zip(memory_rows, vectors):
            text_result = row["_embedding_text_result"]
            metadata = MemoryVectorMetadata(
                memory_id=str(row["memory_id"]),
                user_id=str(row.get("user_id") or "") or None,
                project_id=str(row.get("project_id") or "") or None,
                country=str(row.get("country") or "") or None,
                category=str(row.get("category") or "") or None,
                memory_type=str(row.get("memory_type") or "") or None,
                source=str(row.get("source") or "") or None,
                status=str(row.get("status") or "") or None,
                importance=float(row.get("importance") or 0.0),
                confidence=float(row.get("confidence") or 0.0),
                created_at=str(row.get("created_at") or "") or None,
                updated_at=str(row.get("updated_at") or "") or None,
                content_hash=text_result.content_hash or _sha256_text(str(row.get("content") or "")),
                embedding_provider=self.embedding_provider.provider_name,
                embedding_model=self.embedding_provider.model_name,
                embedding_dim=self.embedding_provider.dimension,
                vector_status="indexed",
                is_current=True,
                metadata=dict(row.get("metadata") or {}),
            )
            records.append(
                MemoryVectorRecord(
                    memory_id=str(row["memory_id"]),
                    embedding_text=text_result.text,
                    embedding_text_hash=text_result.embedding_text_hash or _sha256_text(text_result.text),
                    content_hash=text_result.content_hash or _sha256_text(str(row.get("content") or "")),
                    embedding=list(vector),
                    metadata=metadata,
                )
            )
        self.vector_store.rebuild(records)
        self.vector_store.persist()
        indexed_results: list[MemoryVectorSyncResult] = []
        for record in records:
            self.relational_store.upsert_vector_sync_state(
                self._build_state(
                    memory_id=record.memory_id,
                    content_hash=record.content_hash,
                    embedding_text_hash=record.embedding_text_hash,
                    vector_status="indexed",
                    indexed_at=now_iso(),
                    last_error=None,
                    created_at=(self.get_sync_status(record.memory_id).created_at if self.get_sync_status(record.memory_id) else now_iso()),
                )
            )
            indexed_results.append(MemoryVectorSyncResult(memory_id=record.memory_id, status="indexed"))
        return _build_report(indexed_results + skipped)

    def get_sync_status(self, memory_id: str) -> MemoryVectorSyncState | None:
        return self.relational_store.get_vector_sync_state(memory_id, vector_namespace=self.vector_store.manifest.namespace)

    def _build_state(
        self,
        *,
        memory_id: str,
        content_hash: str,
        embedding_text_hash: str | None,
        vector_status: str,
        indexed_at: str | None,
        last_error: str | None,
        created_at: str,
    ) -> MemoryVectorSyncState:
        return MemoryVectorSyncState(
            memory_id=memory_id,
            vector_namespace=self.vector_store.manifest.namespace,
            embedding_provider=self.embedding_provider.provider_name,
            embedding_model=self.embedding_provider.model_name,
            embedding_dim=self.embedding_provider.dimension,
            content_hash=content_hash,
            embedding_text_hash=embedding_text_hash,
            vector_status=vector_status,
            indexed_at=indexed_at,
            last_error=last_error,
            created_at=created_at,
            updated_at=now_iso(),
        )


def build_default_memory_vector_sync_service(
    *,
    relational_store: SQLiteMemoryStore | None = None,
) -> MemoryVectorSyncService:
    relational = relational_store or SQLiteMemoryStore()
    provider = build_memory_embedding_provider()
    manifest = MemoryVectorManifest(
        namespace=settings.memory_vector_namespace,
        embedding_provider=provider.provider_name,
        embedding_model=provider.model_name,
        embedding_dim=provider.dimension,
        index_type="flat_l2",
        distance_metric="l2",
        record_count=0,
        checksum="",
        built_at=now_iso(),
    )
    vector_store = MemoryFaissStore(
        index_dir=settings.resolve_path(settings.memory_vector_index_dir),
        manifest=manifest,
    )
    return MemoryVectorSyncService(
        relational_store=relational,
        vector_store=vector_store,
        embedding_provider=provider,
    )


def _build_report(results: list[MemoryVectorSyncResult]) -> MemoryVectorSyncReport:
    counts = {
        "indexed": 0,
        "stale": 0,
        "deleted": 0,
        "failed": 0,
        "skipped": 0,
        "pending": 0,
    }
    for item in results:
        if item.status in counts:
            counts[item.status] += 1
    return MemoryVectorSyncReport(
        total=len(results),
        indexed=counts["indexed"],
        stale=counts["stale"],
        deleted=counts["deleted"],
        failed=counts["failed"],
        skipped=counts["skipped"],
        pending=counts["pending"],
        results=tuple(results),
    )


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(str(text).encode("utf-8")).hexdigest()
