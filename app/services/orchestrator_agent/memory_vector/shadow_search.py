"""Shadow search entrypoint for M6A."""

from __future__ import annotations

from app.core.config import settings
from app.services.orchestrator_agent.memory_store import SQLiteMemoryStore

from .provider import MemoryEmbeddingProvider, build_memory_embedding_provider
from .schemas import (
    MemoryShadowCandidate,
    MemoryShadowFilteredCandidate,
    MemoryShadowSearchResult,
)
from .sync import build_default_memory_vector_sync_service


def shadow_search_memory(
    query: str,
    *,
    user_id: str,
    project_id: str | None,
    country: str | None,
    top_k: int = 8,
    category: str | None = None,
    memory_type: str | None = None,
    relational_store: SQLiteMemoryStore | None = None,
    vector_store=None,
    embedding_provider: MemoryEmbeddingProvider | None = None,
) -> MemoryShadowSearchResult:
    if not settings.memory_vector_shadow_enabled:
        return MemoryShadowSearchResult(
            query=query,
            top_k=top_k,
            candidates=(),
            filtered_out=(),
            vector_index_status={"ok": False, "reason": "shadow_search_disabled"},
        )

    if vector_store is None or embedding_provider is None:
        service = build_default_memory_vector_sync_service(relational_store=relational_store)
        relational = service.relational_store
        active_vector_store = service.vector_store
        provider = service.embedding_provider
    else:
        relational = relational_store or SQLiteMemoryStore()
        active_vector_store = vector_store
        provider = embedding_provider

    query_vector = provider.embed_texts([query], input_type="query")[0]
    vector_results = active_vector_store.search(
        query_vector,
        top_k=top_k,
        filters={"category": category, "memory_type": memory_type},
    )

    candidates: list[MemoryShadowCandidate] = []
    filtered: list[MemoryShadowFilteredCandidate] = []
    for item in vector_results:
        memory = relational.get(
            item.memory_id,
            user_id=user_id,
            project_id=project_id or "",
            country=country or "",
        )
        if memory is None:
            filtered.append(
                MemoryShadowFilteredCandidate(
                    memory_id=item.memory_id,
                    reason="not_visible_or_missing",
                    vector_metadata=item.metadata,
                )
            )
            continue
        if str(memory.get("status") or "").strip().lower() != "active":
            filtered.append(
                MemoryShadowFilteredCandidate(
                    memory_id=item.memory_id,
                    reason="inactive_memory_status",
                    vector_metadata=item.metadata,
                )
            )
            continue
        candidates.append(
            MemoryShadowCandidate(
                memory_id=item.memory_id,
                raw_distance=item.raw_distance,
                score=item.score,
                memory=memory,
                vector_metadata=item.metadata,
            )
        )

    return MemoryShadowSearchResult(
        query=query,
        top_k=top_k,
        candidates=tuple(candidates),
        filtered_out=tuple(filtered),
        vector_index_status=active_vector_store.health_check(),
    )
