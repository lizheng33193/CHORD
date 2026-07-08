"""Local FAISS-backed shadow vector store for M6A."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .schemas import (
    MemoryVectorIndexEntry,
    MemoryVectorManifest,
    MemoryVectorMetadata,
    MemoryVectorRecord,
    MemoryVectorSearchResult,
)


class MemoryVectorCompatibilityError(ValueError):
    """Raised when persisted manifest is incompatible with current config."""


class MemoryFaissStore:
    def __init__(self, *, index_dir: Path, manifest: MemoryVectorManifest) -> None:
        self._index_dir = Path(index_dir)
        self._manifest = manifest
        self._index_path = self._index_dir / "index.faiss"
        self._manifest_path = self._index_dir / "manifest.json"
        self._metadata_path = self._index_dir / "metadata.json"
        self._faiss = self._require_faiss()
        self._entries: dict[int, MemoryVectorIndexEntry] = {}
        self._index = self._faiss.IndexIDMap2(self._faiss.IndexFlatL2(self._manifest.embedding_dim))
        self._load_existing()

    def upsert(self, records: list[MemoryVectorRecord]) -> None:
        if not records:
            return
        vectors: list[list[float]] = []
        ids: list[int] = []
        for record in records:
            self._validate_record(record)
            self._deactivate_memory(record.memory_id)
            vector_id = self._next_vector_id()
            ids.append(vector_id)
            vectors.append(list(record.embedding))
            self._entries[vector_id] = MemoryVectorIndexEntry(
                vector_id=vector_id,
                memory_id=record.memory_id,
                embedding_text_hash=record.embedding_text_hash,
                metadata=record.metadata,
            )
        if ids:
            self._index.add_with_ids(
                np.array(vectors, dtype="float32"),
                np.array(ids, dtype="int64"),
            )
        self._refresh_manifest()

    def delete(self, memory_ids: list[str]) -> None:
        for memory_id in memory_ids:
            self._deactivate_memory(memory_id, status="deleted")
        self._refresh_manifest()

    def rebuild(self, records: list[MemoryVectorRecord]) -> None:
        self._index = self._faiss.IndexIDMap2(self._faiss.IndexFlatL2(self._manifest.embedding_dim))
        self._entries = {}
        self.upsert(records)
        self._refresh_manifest()

    def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[MemoryVectorSearchResult]:
        if self._index.ntotal == 0:
            return []
        fetch_k = min(max(int(top_k) * 5, int(top_k) + 20), max(int(self._index.ntotal), int(top_k)))
        distances, ids = self._index.search(
            np.array([query_embedding], dtype="float32"),
            fetch_k,
        )
        results: list[MemoryVectorSearchResult] = []
        seen_memory_ids: set[str] = set()
        for raw_distance, vector_id in zip(distances[0].tolist(), ids[0].tolist()):
            if vector_id < 0:
                continue
            entry = self._entries.get(int(vector_id))
            if entry is None:
                continue
            if not entry.metadata.is_current or entry.metadata.vector_status != "indexed":
                continue
            if entry.memory_id in seen_memory_ids:
                continue
            if not _matches_filters(entry.metadata, filters or {}):
                continue
            seen_memory_ids.add(entry.memory_id)
            results.append(
                MemoryVectorSearchResult(
                    memory_id=entry.memory_id,
                    raw_distance=float(raw_distance),
                    score=round(1.0 / (1.0 + float(raw_distance)), 6),
                    metadata=entry.metadata,
                )
            )
            if len(results) >= top_k:
                break
        return results

    def persist(self) -> None:
        self._index_dir.mkdir(parents=True, exist_ok=True)
        temp_index_path = self._index_path.with_suffix(".faiss.tmp")
        self._faiss.write_index(self._index, str(temp_index_path))
        metadata_payload = {
            str(vector_id): entry.to_dict()
            for vector_id, entry in sorted(self._entries.items())
        }
        temp_metadata_path = self._metadata_path.with_suffix(".json.tmp")
        temp_manifest_path = self._manifest_path.with_suffix(".json.tmp")
        temp_metadata_path.write_text(json.dumps(metadata_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        checksum = self._compute_checksum(temp_index_path, temp_metadata_path)
        manifest_payload = self._manifest.to_dict() | {
            "record_count": len(self._entries),
            "checksum": checksum,
            "built_at": _now_iso(),
        }
        temp_manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_index_path.replace(self._index_path)
        temp_metadata_path.replace(self._metadata_path)
        temp_manifest_path.replace(self._manifest_path)
        self._manifest = MemoryVectorManifest(**manifest_payload)

    def health_check(self) -> dict[str, Any]:
        return {
            "ok": True,
            "index_path": str(self._index_path),
            "metadata_path": str(self._metadata_path),
            "manifest_path": str(self._manifest_path),
            "record_count": len(self._entries),
            "manifest": self._manifest.to_dict(),
        }

    @property
    def manifest(self) -> MemoryVectorManifest:
        return self._manifest

    def _load_existing(self) -> None:
        if not self._manifest_path.exists() or not self._metadata_path.exists() or not self._index_path.exists():
            return
        persisted_manifest = MemoryVectorManifest(**json.loads(self._manifest_path.read_text(encoding="utf-8")))
        if persisted_manifest.compatibility_key() != self._manifest.compatibility_key():
            raise MemoryVectorCompatibilityError("persisted memory vector manifest is incompatible; rebuild required")
        self._manifest = persisted_manifest
        self._index = self._faiss.read_index(str(self._index_path))
        raw_entries = json.loads(self._metadata_path.read_text(encoding="utf-8"))
        self._entries = {
            int(vector_id): MemoryVectorIndexEntry(
                vector_id=int(payload["vector_id"]),
                memory_id=str(payload["memory_id"]),
                embedding_text_hash=str(payload["embedding_text_hash"]),
                metadata=MemoryVectorMetadata(**payload["metadata"]),
            )
            for vector_id, payload in raw_entries.items()
        }

    def _validate_record(self, record: MemoryVectorRecord) -> None:
        if len(record.embedding) != self._manifest.embedding_dim:
            raise MemoryVectorCompatibilityError(
                f"embedding dimension mismatch: expected {self._manifest.embedding_dim}, got {len(record.embedding)}"
            )
        metadata = record.metadata
        expected_key = self._manifest.compatibility_key()[:3]
        if (metadata.embedding_provider, metadata.embedding_model, metadata.embedding_dim) != expected_key:
            raise MemoryVectorCompatibilityError("record embedding metadata does not match store manifest")

    def _deactivate_memory(self, memory_id: str, *, status: str = "stale") -> None:
        for vector_id, entry in list(self._entries.items()):
            if entry.memory_id != memory_id or not entry.metadata.is_current:
                continue
            metadata = MemoryVectorMetadata(
                **(entry.metadata.to_dict() | {"is_current": False, "vector_status": status})
            )
            self._entries[vector_id] = MemoryVectorIndexEntry(
                vector_id=vector_id,
                memory_id=entry.memory_id,
                embedding_text_hash=entry.embedding_text_hash,
                metadata=metadata,
            )

    def _refresh_manifest(self) -> None:
        self._manifest = MemoryVectorManifest(
            namespace=self._manifest.namespace,
            embedding_provider=self._manifest.embedding_provider,
            embedding_model=self._manifest.embedding_model,
            embedding_dim=self._manifest.embedding_dim,
            index_type=self._manifest.index_type,
            distance_metric=self._manifest.distance_metric,
            record_count=len(self._entries),
            checksum=self._manifest.checksum,
            built_at=_now_iso(),
        )

    def _next_vector_id(self) -> int:
        return (max(self._entries) + 1) if self._entries else 0

    def _require_faiss(self):
        try:
            import faiss
        except Exception as exc:  # pragma: no cover - runtime guard
            raise RuntimeError("faiss is required for memory vector shadow indexing") from exc
        return faiss

    def _compute_checksum(self, index_path: Path, metadata_path: Path) -> str:
        digest = hashlib.sha256()
        digest.update(index_path.read_bytes())
        digest.update(metadata_path.read_bytes())
        return f"sha256:{digest.hexdigest()}"


def _matches_filters(metadata: MemoryVectorMetadata, filters: dict[str, Any]) -> bool:
    for key, expected in filters.items():
        if expected is None:
            continue
        actual = getattr(metadata, key, None)
        if actual != expected:
            return False
    return True


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
