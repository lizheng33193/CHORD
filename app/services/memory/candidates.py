"""Candidate objects for the M4 memory contract layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from app.services.memory.contracts import (
    MemoryAuthorityLevel,
    MemorySourceType,
    MemoryUsePurpose,
)


@dataclass(frozen=True)
class MemoryCandidate:
    content: str
    memory_source_type: MemorySourceType
    authority_level: MemoryAuthorityLevel
    allowed_memory_use: tuple[MemoryUsePurpose, ...]
    forbidden_memory_use: tuple[MemoryUsePurpose, ...]
    user_id: str | None = None
    project_id: str | None = None
    country: str | None = None
    session_id: str | None = None
    source_run_id: str | None = None
    source_artifact_id: str | None = None
    evidence_status: str | None = None
    importance: float = 0.5
    confidence: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        content = str(self.content or "").strip()
        if not content:
            raise ValueError("memory candidate content is required")

        allowed = _normalize_uses(self.allowed_memory_use, "allowed_memory_use")
        forbidden = _normalize_uses(self.forbidden_memory_use, "forbidden_memory_use")

        object.__setattr__(self, "content", content)
        object.__setattr__(self, "allowed_memory_use", allowed)
        object.__setattr__(self, "forbidden_memory_use", forbidden)


def _normalize_uses(
    uses: Iterable[MemoryUsePurpose],
    field_name: str,
) -> tuple[MemoryUsePurpose, ...]:
    normalized = tuple(uses)
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if not all(isinstance(use, MemoryUsePurpose) for use in normalized):
        raise ValueError(f"{field_name} must contain MemoryUsePurpose values")
    return normalized
