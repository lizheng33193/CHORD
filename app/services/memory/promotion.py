"""M4-4 promotion policy and candidate eligibility decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from app.services.memory.candidates import MemoryCandidate
from app.services.memory.contracts import (
    MemoryAuthorityLevel,
    MemorySourceType,
    MemoryUsePurpose,
)

if TYPE_CHECKING:
    from app.services.memory.retrieval import MemoryRetrievedItem


class MemoryPromotionTarget(str, Enum):
    PROFILE_HISTORY = "profile_history"
    RISK_QA_HISTORY = "risk_qa_history"
    SQL_CASE = "sql_case"
    SQL_ERROR_CASE = "sql_error_case"
    EVAL_CANDIDATE = "eval_candidate"
    APPROVED_SQL_EXAMPLE = "approved_sql_example"
    RISK_KNOWLEDGE_SOURCE_DOCUMENT = "risk_knowledge_source_document"
    RISK_KNOWLEDGE_DOCUMENT_EVIDENCE = "risk_knowledge_document_evidence"
    DATA_KNOWLEDGE_AUTHORITY = "data_knowledge_authority"
    APPROVED_STRATEGY_POLICY = "approved_strategy_policy"
    SAFETY_POLICY = "safety_policy"
    HITL_BYPASS_POLICY = "hitl_bypass_policy"


class MemoryPromotionStatus(str, Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"


class MemoryPromotionBlockReason(str, Enum):
    EXPLICITLY_FORBIDDEN = "explicitly_forbidden"
    SOURCE_TYPE_NOT_ALLOWED = "source_type_not_allowed"
    AUTHORITY_LEVEL_INSUFFICIENT = "authority_level_insufficient"
    EVIDENCE_INSUFFICIENT = "evidence_insufficient"
    HUMAN_APPROVAL_REQUIRED = "human_approval_required"
    TARGET_REQUIRES_GOVERNANCE_WORKFLOW = "target_requires_governance_workflow"
    UNKNOWN_TARGET = "unknown_target"


@dataclass(frozen=True)
class MemoryPromotionRequest:
    target: MemoryPromotionTarget | str
    memory_source_type: MemorySourceType
    authority_level: MemoryAuthorityLevel
    allowed_memory_use: tuple[MemoryUsePurpose, ...]
    forbidden_memory_use: tuple[MemoryUsePurpose, ...]
    content: str | None = None
    source_memory_id: str | None = None
    source_run_id: str | None = None
    source_artifact_id: str | None = None
    evidence_status: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryPromotionDecision:
    status: MemoryPromotionStatus
    allowed: bool
    target: MemoryPromotionTarget | str
    memory_source_type: MemorySourceType
    authority_level: MemoryAuthorityLevel
    reason: str
    blocked_by: MemoryPromotionBlockReason | None = None
    source_memory_id: str | None = None
    source_run_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def promotion_request_from_candidate(
    candidate: MemoryCandidate,
    target: MemoryPromotionTarget,
    *,
    source_memory_id: str | None = None,
) -> MemoryPromotionRequest:
    return MemoryPromotionRequest(
        target=target,
        memory_source_type=candidate.memory_source_type,
        authority_level=candidate.authority_level,
        allowed_memory_use=candidate.allowed_memory_use,
        forbidden_memory_use=candidate.forbidden_memory_use,
        content=candidate.content,
        source_memory_id=source_memory_id,
        source_run_id=candidate.source_run_id,
        source_artifact_id=candidate.source_artifact_id,
        evidence_status=candidate.evidence_status,
        metadata=dict(candidate.metadata),
    )


def promotion_request_from_retrieved_item(
    item: MemoryRetrievedItem,
    target: MemoryPromotionTarget,
) -> MemoryPromotionRequest:
    return MemoryPromotionRequest(
        target=target,
        memory_source_type=item.memory_source_type,
        authority_level=item.authority_level,
        allowed_memory_use=item.allowed_memory_use,
        forbidden_memory_use=item.forbidden_memory_use,
        content=item.content,
        source_memory_id=item.memory_id,
        source_run_id=item.source_run_id,
        source_artifact_id=item.source_artifact_id,
        evidence_status=item.evidence_status,
        metadata=dict(item.metadata),
    )


_ALLOWED_TARGETS: dict[MemorySourceType, tuple[MemoryPromotionTarget, ...]] = {
    MemorySourceType.PROFILE_RESULT: (MemoryPromotionTarget.PROFILE_HISTORY,),
    MemorySourceType.RISK_QA_ANSWER: (
        MemoryPromotionTarget.RISK_QA_HISTORY,
        MemoryPromotionTarget.EVAL_CANDIDATE,
    ),
    MemorySourceType.DATA_AGENT_SQL_CASE: (
        MemoryPromotionTarget.SQL_CASE,
        MemoryPromotionTarget.APPROVED_SQL_EXAMPLE,
    ),
    MemorySourceType.DATA_AGENT_SQL_ERROR: (
        MemoryPromotionTarget.SQL_ERROR_CASE,
        MemoryPromotionTarget.EVAL_CANDIDATE,
    ),
    MemorySourceType.AUDIT_EVENT: (MemoryPromotionTarget.EVAL_CANDIDATE,),
    MemorySourceType.EVAL_CASE: (MemoryPromotionTarget.EVAL_CANDIDATE,),
}

_EXPLICIT_FORBIDDEN_TARGETS: dict[MemorySourceType, tuple[MemoryPromotionTarget, ...]] = {
    MemorySourceType.PROFILE_RESULT: (
        MemoryPromotionTarget.DATA_KNOWLEDGE_AUTHORITY,
        MemoryPromotionTarget.RISK_KNOWLEDGE_DOCUMENT_EVIDENCE,
        MemoryPromotionTarget.RISK_KNOWLEDGE_SOURCE_DOCUMENT,
        MemoryPromotionTarget.APPROVED_STRATEGY_POLICY,
        MemoryPromotionTarget.APPROVED_SQL_EXAMPLE,
        MemoryPromotionTarget.SAFETY_POLICY,
    ),
    MemorySourceType.RISK_QA_ANSWER: (
        MemoryPromotionTarget.RISK_KNOWLEDGE_SOURCE_DOCUMENT,
        MemoryPromotionTarget.RISK_KNOWLEDGE_DOCUMENT_EVIDENCE,
        MemoryPromotionTarget.DATA_KNOWLEDGE_AUTHORITY,
        MemoryPromotionTarget.APPROVED_STRATEGY_POLICY,
        MemoryPromotionTarget.SAFETY_POLICY,
    ),
    MemorySourceType.DATA_AGENT_SQL_CASE: (
        MemoryPromotionTarget.RISK_KNOWLEDGE_SOURCE_DOCUMENT,
        MemoryPromotionTarget.RISK_KNOWLEDGE_DOCUMENT_EVIDENCE,
        MemoryPromotionTarget.DATA_KNOWLEDGE_AUTHORITY,
        MemoryPromotionTarget.APPROVED_STRATEGY_POLICY,
        MemoryPromotionTarget.SAFETY_POLICY,
        MemoryPromotionTarget.HITL_BYPASS_POLICY,
    ),
    MemorySourceType.DATA_AGENT_SQL_ERROR: (
        MemoryPromotionTarget.APPROVED_SQL_EXAMPLE,
        MemoryPromotionTarget.DATA_KNOWLEDGE_AUTHORITY,
        MemoryPromotionTarget.HITL_BYPASS_POLICY,
        MemoryPromotionTarget.SAFETY_POLICY,
        MemoryPromotionTarget.RISK_KNOWLEDGE_SOURCE_DOCUMENT,
        MemoryPromotionTarget.RISK_KNOWLEDGE_DOCUMENT_EVIDENCE,
    ),
    MemorySourceType.USER_PREFERENCE: (
        MemoryPromotionTarget.DATA_KNOWLEDGE_AUTHORITY,
        MemoryPromotionTarget.RISK_KNOWLEDGE_SOURCE_DOCUMENT,
        MemoryPromotionTarget.RISK_KNOWLEDGE_DOCUMENT_EVIDENCE,
        MemoryPromotionTarget.APPROVED_STRATEGY_POLICY,
        MemoryPromotionTarget.SAFETY_POLICY,
        MemoryPromotionTarget.HITL_BYPASS_POLICY,
        MemoryPromotionTarget.APPROVED_SQL_EXAMPLE,
    ),
    MemorySourceType.CONVERSATION: (
        MemoryPromotionTarget.DATA_KNOWLEDGE_AUTHORITY,
        MemoryPromotionTarget.RISK_KNOWLEDGE_SOURCE_DOCUMENT,
        MemoryPromotionTarget.RISK_KNOWLEDGE_DOCUMENT_EVIDENCE,
        MemoryPromotionTarget.APPROVED_STRATEGY_POLICY,
        MemoryPromotionTarget.SAFETY_POLICY,
        MemoryPromotionTarget.HITL_BYPASS_POLICY,
        MemoryPromotionTarget.APPROVED_SQL_EXAMPLE,
    ),
    MemorySourceType.AUDIT_EVENT: (
        MemoryPromotionTarget.RISK_KNOWLEDGE_SOURCE_DOCUMENT,
        MemoryPromotionTarget.RISK_KNOWLEDGE_DOCUMENT_EVIDENCE,
        MemoryPromotionTarget.DATA_KNOWLEDGE_AUTHORITY,
        MemoryPromotionTarget.APPROVED_STRATEGY_POLICY,
        MemoryPromotionTarget.SAFETY_POLICY,
        MemoryPromotionTarget.HITL_BYPASS_POLICY,
        MemoryPromotionTarget.APPROVED_SQL_EXAMPLE,
    ),
    MemorySourceType.EVAL_CASE: (
        MemoryPromotionTarget.RISK_KNOWLEDGE_SOURCE_DOCUMENT,
        MemoryPromotionTarget.RISK_KNOWLEDGE_DOCUMENT_EVIDENCE,
        MemoryPromotionTarget.DATA_KNOWLEDGE_AUTHORITY,
        MemoryPromotionTarget.APPROVED_STRATEGY_POLICY,
        MemoryPromotionTarget.SAFETY_POLICY,
        MemoryPromotionTarget.HITL_BYPASS_POLICY,
        MemoryPromotionTarget.APPROVED_SQL_EXAMPLE,
    ),
}


def validate_memory_promotion(request: MemoryPromotionRequest) -> MemoryPromotionDecision:
    target = _coerce_target(request.target)
    if target is None:
        return _blocked(
            request,
            reason="unknown promotion target",
            blocked_by=MemoryPromotionBlockReason.UNKNOWN_TARGET,
        )

    if target in _EXPLICIT_FORBIDDEN_TARGETS.get(request.memory_source_type, ()):
        return _blocked(
            request,
            target=target,
            reason="promotion target is explicitly forbidden for this memory source",
            blocked_by=MemoryPromotionBlockReason.EXPLICITLY_FORBIDDEN,
        )

    if target not in _ALLOWED_TARGETS.get(request.memory_source_type, ()):
        return _blocked(
            request,
            target=target,
            reason="memory source type cannot promote to this target",
            blocked_by=MemoryPromotionBlockReason.SOURCE_TYPE_NOT_ALLOWED,
        )

    authority_error = _check_authority(request, target)
    if authority_error is not None:
        return authority_error

    evidence_error = _check_evidence(request, target)
    if evidence_error is not None:
        return evidence_error

    return _allowed(request, target, reason=_allowed_reason(request, target))


def _coerce_target(target: MemoryPromotionTarget | str) -> MemoryPromotionTarget | None:
    if isinstance(target, MemoryPromotionTarget):
        return target
    try:
        return MemoryPromotionTarget(str(target))
    except ValueError:
        return None


def _check_authority(
    request: MemoryPromotionRequest,
    target: MemoryPromotionTarget,
) -> MemoryPromotionDecision | None:
    if target in {
        MemoryPromotionTarget.SQL_CASE,
        MemoryPromotionTarget.APPROVED_SQL_EXAMPLE,
    } and request.authority_level is not MemoryAuthorityLevel.HUMAN_APPROVED:
        return _blocked(
            request,
            target=target,
            reason="promotion target requires human-approved SQL memory",
            blocked_by=MemoryPromotionBlockReason.AUTHORITY_LEVEL_INSUFFICIENT,
        )

    if target is MemoryPromotionTarget.EVAL_CANDIDATE and request.memory_source_type is MemorySourceType.RISK_QA_ANSWER:
        metadata = request.metadata
        metadata_allows = bool(metadata.get("human_corrected")) or bool(metadata.get("evaluation_candidate"))
        authority_allows = request.authority_level in {
            MemoryAuthorityLevel.EVIDENCE_GROUNDED,
            MemoryAuthorityLevel.HUMAN_APPROVED,
        }
        if not authority_allows and not metadata_allows:
            return _blocked(
                request,
                target=target,
                reason="risk QA promotion to eval candidate requires grounded or reviewed evidence",
                blocked_by=MemoryPromotionBlockReason.AUTHORITY_LEVEL_INSUFFICIENT,
            )

    return None


def _check_evidence(
    request: MemoryPromotionRequest,
    target: MemoryPromotionTarget,
) -> MemoryPromotionDecision | None:
    if target is MemoryPromotionTarget.APPROVED_SQL_EXAMPLE and not str(
        request.metadata.get("approved_sql_hash") or request.source_artifact_id or ""
    ).strip():
        return _blocked(
            request,
            target=target,
            reason="approved SQL example candidate requires approved_sql_hash evidence",
            blocked_by=MemoryPromotionBlockReason.EVIDENCE_INSUFFICIENT,
        )

    return None


def _allowed_reason(
    request: MemoryPromotionRequest,
    target: MemoryPromotionTarget,
) -> str:
    if target is MemoryPromotionTarget.APPROVED_SQL_EXAMPLE:
        return "eligible as approved_sql_example candidate; requires governance ingestion"
    if target is MemoryPromotionTarget.EVAL_CANDIDATE and request.memory_source_type is MemorySourceType.AUDIT_EVENT:
        return "eligible as eval candidate only; not eligible for production grounding"
    return "eligible as promotion candidate"


def _allowed(
    request: MemoryPromotionRequest,
    target: MemoryPromotionTarget,
    *,
    reason: str,
) -> MemoryPromotionDecision:
    return MemoryPromotionDecision(
        status=MemoryPromotionStatus.ALLOWED,
        allowed=True,
        target=target,
        memory_source_type=request.memory_source_type,
        authority_level=request.authority_level,
        reason=reason,
        blocked_by=None,
        source_memory_id=request.source_memory_id,
        source_run_id=request.source_run_id,
        metadata=dict(request.metadata),
    )


def _blocked(
    request: MemoryPromotionRequest,
    *,
    reason: str,
    blocked_by: MemoryPromotionBlockReason,
    target: MemoryPromotionTarget | None = None,
) -> MemoryPromotionDecision:
    return MemoryPromotionDecision(
        status=MemoryPromotionStatus.BLOCKED,
        allowed=False,
        target=target or request.target,
        memory_source_type=request.memory_source_type,
        authority_level=request.authority_level,
        reason=reason,
        blocked_by=blocked_by,
        source_memory_id=request.source_memory_id,
        source_run_id=request.source_run_id,
        metadata=dict(request.metadata),
    )
