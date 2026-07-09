"""Deterministic fusion helpers for M6B hybrid retrieval."""

from __future__ import annotations

from app.services.memory.retrieval import MemoryRetrievedItem


def fuse_memory_items(
    *,
    fts_items: tuple[MemoryRetrievedItem, ...],
    vector_items: tuple[MemoryRetrievedItem, ...],
    max_total_items: int,
    max_vector_items: int,
) -> tuple[MemoryRetrievedItem, ...]:
    fused: list[MemoryRetrievedItem] = []
    seen_memory_ids: set[str] = set()

    for item in fts_items:
        if item.memory_id in seen_memory_ids:
            continue
        seen_memory_ids.add(item.memory_id)
        fused.append(item)
        if len(fused) >= max_total_items:
            return tuple(fused[:max_total_items])

    appended_vector = 0
    for item in vector_items:
        if appended_vector >= max_vector_items or len(fused) >= max_total_items:
            break
        if item.memory_id in seen_memory_ids:
            continue
        seen_memory_ids.add(item.memory_id)
        fused.append(item)
        appended_vector += 1

    return tuple(fused[:max_total_items])
