"""Temporary M6B adapter seam from app/services/memory into M6A vector primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.services.orchestrator_agent.memory_store import SQLiteMemoryStore


@dataclass(frozen=True)
class MemoryVectorQueryHit:
    memory_id: str
    raw_distance: float
    normalized_score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class MemoryVectorIndex(Protocol):
    def search(self, *, query: str, top_k: int) -> list[MemoryVectorQueryHit]:
        ...

    def health_check(self) -> dict[str, Any]:
        ...


class OrchestratorMemoryVectorIndexAdapter:
    """Temporary compatibility seam.

    This is the only app/services/memory module allowed to import
    app/services/orchestrator_agent/memory_vector/* during M6B.
    """

    def __init__(self, *, relational_store: SQLiteMemoryStore | None = None) -> None:
        self._relational_store = relational_store

    def search(self, *, query: str, top_k: int) -> list[MemoryVectorQueryHit]:
        from app.services.orchestrator_agent.memory_vector.sync import (
            build_default_memory_vector_sync_service,
        )

        service = build_default_memory_vector_sync_service(relational_store=self._relational_store)
        query_vector = service.embedding_provider.embed_texts([query], input_type="query")[0]
        return [
            MemoryVectorQueryHit(
                memory_id=item.memory_id,
                raw_distance=item.raw_distance,
                normalized_score=item.score,
                metadata=item.metadata.to_dict(),
            )
            for item in service.vector_store.search(list(query_vector), top_k=top_k)
        ]

    def health_check(self) -> dict[str, Any]:
        from app.services.orchestrator_agent.memory_vector.sync import (
            build_default_memory_vector_sync_service,
        )

        service = build_default_memory_vector_sync_service(relational_store=self._relational_store)
        return service.vector_store.health_check()
