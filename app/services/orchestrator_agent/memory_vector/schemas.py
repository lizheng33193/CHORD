"""Contracts for M6A memory vector shadow indexing."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


MemoryVectorState = Literal["pending", "indexed", "stale", "deleted", "failed", "skipped"]


@dataclass(frozen=True)
class MemoryEmbeddingTextResult:
    text: str
    skipped: bool
    reason: str | None
    content_hash: str | None
    embedding_text_hash: str | None


@dataclass(frozen=True)
class MemoryVectorMetadata:
    memory_id: str
    user_id: str | None
    project_id: str | None
    country: str | None
    category: str | None
    memory_type: str | None
    source: str | None
    status: str | None
    importance: float | None
    confidence: float | None
    created_at: str | None
    updated_at: str | None
    content_hash: str
    embedding_provider: str
    embedding_model: str
    embedding_dim: int
    vector_status: MemoryVectorState = "indexed"
    is_current: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MemoryVectorRecord:
    memory_id: str
    embedding_text: str
    embedding_text_hash: str
    content_hash: str
    embedding: list[float]
    metadata: MemoryVectorMetadata


@dataclass(frozen=True)
class MemoryVectorIndexEntry:
    vector_id: int
    memory_id: str
    embedding_text_hash: str
    metadata: MemoryVectorMetadata

    def to_dict(self) -> dict[str, Any]:
        return {
            "vector_id": self.vector_id,
            "memory_id": self.memory_id,
            "embedding_text_hash": self.embedding_text_hash,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class MemoryVectorManifest:
    namespace: str
    embedding_provider: str
    embedding_model: str
    embedding_dim: int
    index_type: str
    distance_metric: str
    record_count: int
    checksum: str
    built_at: str

    def compatibility_key(self) -> tuple[str, str, int, str, str, str]:
        return (
            self.embedding_provider,
            self.embedding_model,
            int(self.embedding_dim),
            self.namespace,
            self.index_type,
            self.distance_metric,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MemoryVectorSearchResult:
    memory_id: str
    raw_distance: float
    score: float
    metadata: MemoryVectorMetadata


@dataclass(frozen=True)
class MemoryVectorSyncState:
    memory_id: str
    vector_namespace: str
    embedding_provider: str
    embedding_model: str
    embedding_dim: int
    content_hash: str
    embedding_text_hash: str | None
    vector_status: MemoryVectorState
    indexed_at: str | None = None
    last_error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class MemoryVectorSyncResult:
    memory_id: str
    status: MemoryVectorState
    reason: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class MemoryVectorSyncReport:
    total: int
    indexed: int = 0
    stale: int = 0
    deleted: int = 0
    failed: int = 0
    skipped: int = 0
    pending: int = 0
    results: tuple[MemoryVectorSyncResult, ...] = ()


@dataclass(frozen=True)
class MemoryShadowCandidate:
    memory_id: str
    raw_distance: float
    score: float
    memory: dict[str, Any]
    vector_metadata: MemoryVectorMetadata


@dataclass(frozen=True)
class MemoryShadowFilteredCandidate:
    memory_id: str
    reason: str
    vector_metadata: MemoryVectorMetadata


@dataclass(frozen=True)
class MemoryShadowSearchResult:
    query: str
    top_k: int
    candidates: tuple[MemoryShadowCandidate, ...]
    filtered_out: tuple[MemoryShadowFilteredCandidate, ...]
    vector_index_status: dict[str, Any]
