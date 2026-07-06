"""Isolation validator for M4 memory candidates."""

from __future__ import annotations

from app.services.memory.candidates import MemoryCandidate
from app.services.memory.contracts import (
    MemoryAuthorityLevel,
    MemorySourceType,
    MemoryUseDecision,
    MemoryUsePurpose,
)


def validate_memory_use(
    candidate: MemoryCandidate,
    requested_use: MemoryUsePurpose,
    *,
    production_context: bool = False,
) -> MemoryUseDecision:
    if requested_use in candidate.forbidden_memory_use:
        return _blocked(candidate, requested_use, "requested use is explicitly forbidden", "explicit_forbidden_use")

    if requested_use not in candidate.allowed_memory_use:
        return _blocked(candidate, requested_use, "requested use is not allowed", "not_in_allowed_use")

    if requested_use is MemoryUsePurpose.SQL_GENERATION_GROUNDING and (
        candidate.memory_source_type is not MemorySourceType.DATA_AGENT_SQL_CASE
        or candidate.authority_level is not MemoryAuthorityLevel.HUMAN_APPROVED
    ):
        return _blocked(
            candidate,
            requested_use,
            "sql generation grounding requires a human-approved SQL case",
            "authority_level_insufficient",
        )

    if production_context and requested_use is MemoryUsePurpose.PRODUCTION_GROUNDING and (
        candidate.authority_level is MemoryAuthorityLevel.UNVERIFIED
    ):
        return _blocked(
            candidate,
            requested_use,
            "unverified memory cannot be used for production grounding",
            "unverified_production_grounding",
        )

    if candidate.authority_level is MemoryAuthorityLevel.AUDIT_ONLY and requested_use is not MemoryUsePurpose.AUDIT_REVIEW:
        return _blocked(
            candidate,
            requested_use,
            "audit-only memory cannot be used outside audit review",
            "audit_only_non_audit_use",
        )

    return MemoryUseDecision(
        allowed=True,
        requested_use=requested_use,
        memory_source_type=candidate.memory_source_type,
        authority_level=candidate.authority_level,
        reason="memory use allowed",
        blocked_by=None,
    )


def _blocked(
    candidate: MemoryCandidate,
    requested_use: MemoryUsePurpose,
    reason: str,
    blocked_by: str,
) -> MemoryUseDecision:
    return MemoryUseDecision(
        allowed=False,
        requested_use=requested_use,
        memory_source_type=candidate.memory_source_type,
        authority_level=candidate.authority_level,
        reason=reason,
        blocked_by=blocked_by,
    )
