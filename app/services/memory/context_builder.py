"""Source-aware memory context rendering for isolated M4 retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.memory.retrieval import MemoryRetrievalResult


@dataclass(frozen=True)
class MemoryContextItem:
    memory_id: str
    header: str
    content: str
    source_type: str
    authority_level: str
    evidence_status: str | None
    requested_use: str
    retrieval_method: str
    source_run_id: str | None = None


@dataclass(frozen=True)
class MemoryContextBundle:
    task_type: str
    items: tuple[MemoryContextItem, ...]
    warnings: tuple[str, ...]
    rendered_text: str
    metadata: dict[str, Any] = field(default_factory=dict)


def build_memory_context_bundle(
    result: MemoryRetrievalResult,
    *,
    max_chars: int = 4000,
) -> MemoryContextBundle:
    lines = ["Retrieved Memories:"]
    rendered_items: list[MemoryContextItem] = []
    warnings = list(result.warnings)
    omitted_item_count = 0

    for index, item in enumerate(result.items, start=1):
        context_item = MemoryContextItem(
            memory_id=item.memory_id,
            header=(
                f"[{index}] source_type={item.memory_source_type.value} | "
                f"authority={item.authority_level.value} | "
                f"use={item.requested_use.value} | "
                f"retrieval={item.retrieval_method} | "
                f"evidence={item.evidence_status or 'none'} | "
                f"memory_id={item.memory_id}"
            ),
            content=item.content,
            source_type=item.memory_source_type.value,
            authority_level=item.authority_level.value,
            evidence_status=item.evidence_status,
            requested_use=item.requested_use.value,
            retrieval_method=item.retrieval_method,
            source_run_id=item.source_run_id,
        )
        block = f"{context_item.header}\n{context_item.content}"
        candidate_text = "\n\n".join([*lines, *(f"{row.header}\n{row.content}" for row in rendered_items), block])
        if len(candidate_text) > max_chars and rendered_items:
            omitted_item_count += 1
            continue
        if len(candidate_text) > max_chars:
            omitted_item_count += 1
            break
        rendered_items.append(context_item)

    rendered_text = "\n\n".join([*lines, *(f"{item.header}\n{item.content}" for item in rendered_items)])
    if omitted_item_count:
        warnings.append("context_truncated")
    metadata = {
        "omitted_item_count": omitted_item_count,
        "included_item_count": len(rendered_items),
    }
    return MemoryContextBundle(
        task_type=result.request.task_type.value,
        items=tuple(rendered_items),
        warnings=tuple(warnings),
        rendered_text=rendered_text,
        metadata=metadata,
    )
