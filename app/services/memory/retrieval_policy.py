"""Task-type retrieval policies for isolated M4 memory recall."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.services.memory.contracts import (
    MemoryAuthorityLevel,
    MemorySourceType,
    MemoryUsePurpose,
)


class MemoryRetrievalTaskType(str, Enum):
    GENERAL_CHAT = "general_chat"
    PROFILE_FOLLOWUP = "profile_followup"
    RISK_QA_FOLLOWUP = "risk_qa_followup"
    DATA_AGENT_SQL = "data_agent_sql"
    SQL_REPAIR = "sql_repair"
    AUDIT_REVIEW = "audit_review"
    EVAL_COLLECTION = "eval_collection"


@dataclass(frozen=True)
class MemoryRetrievalPolicy:
    task_type: MemoryRetrievalTaskType
    allowed_source_types: tuple[MemorySourceType, ...]
    requested_use: MemoryUsePurpose
    min_authority_levels: tuple[MemoryAuthorityLevel, ...]
    production_context: bool = False
    include_legacy_memory: bool = False
    max_items: int = 8


def resolve_retrieval_policies(task_type: MemoryRetrievalTaskType) -> tuple[MemoryRetrievalPolicy, ...]:
    policies: dict[MemoryRetrievalTaskType, tuple[MemoryRetrievalPolicy, ...]] = {
        MemoryRetrievalTaskType.GENERAL_CHAT: (
            _policy(
                task_type,
                MemorySourceType.CONVERSATION,
                MemoryUsePurpose.CONVERSATION_CONTEXT,
                (
                    MemoryAuthorityLevel.USER_PROVIDED,
                    MemoryAuthorityLevel.SYSTEM_GENERATED,
                    MemoryAuthorityLevel.UNVERIFIED,
                ),
            ),
            _policy(
                task_type,
                MemorySourceType.USER_PREFERENCE,
                MemoryUsePurpose.RESPONSE_STYLE,
                (MemoryAuthorityLevel.USER_PROVIDED,),
            ),
            _policy(
                task_type,
                MemorySourceType.USER_PREFERENCE,
                MemoryUsePurpose.REPORT_FORMAT_PREFERENCE,
                (MemoryAuthorityLevel.USER_PROVIDED,),
            ),
        ),
        MemoryRetrievalTaskType.PROFILE_FOLLOWUP: (
            _policy(
                task_type,
                MemorySourceType.PROFILE_RESULT,
                MemoryUsePurpose.PROFILE_FOLLOWUP_CONTEXT,
                (
                    MemoryAuthorityLevel.SYSTEM_GENERATED,
                    MemoryAuthorityLevel.EVIDENCE_GROUNDED,
                ),
            ),
            _policy(
                task_type,
                MemorySourceType.CONVERSATION,
                MemoryUsePurpose.FOLLOWUP_CONTEXT,
                (
                    MemoryAuthorityLevel.USER_PROVIDED,
                    MemoryAuthorityLevel.SYSTEM_GENERATED,
                    MemoryAuthorityLevel.UNVERIFIED,
                ),
            ),
            _policy(
                task_type,
                MemorySourceType.USER_PREFERENCE,
                MemoryUsePurpose.RESPONSE_STYLE,
                (MemoryAuthorityLevel.USER_PROVIDED,),
            ),
            _policy(
                task_type,
                MemorySourceType.USER_PREFERENCE,
                MemoryUsePurpose.REPORT_FORMAT_PREFERENCE,
                (MemoryAuthorityLevel.USER_PROVIDED,),
            ),
        ),
        MemoryRetrievalTaskType.RISK_QA_FOLLOWUP: (
            _policy(
                task_type,
                MemorySourceType.RISK_QA_ANSWER,
                MemoryUsePurpose.RISK_QA_FOLLOWUP_CONTEXT,
                (
                    MemoryAuthorityLevel.EVIDENCE_GROUNDED,
                    MemoryAuthorityLevel.UNVERIFIED,
                ),
            ),
            _policy(
                task_type,
                MemorySourceType.CONVERSATION,
                MemoryUsePurpose.FOLLOWUP_CONTEXT,
                (
                    MemoryAuthorityLevel.USER_PROVIDED,
                    MemoryAuthorityLevel.SYSTEM_GENERATED,
                    MemoryAuthorityLevel.UNVERIFIED,
                ),
            ),
            _policy(
                task_type,
                MemorySourceType.USER_PREFERENCE,
                MemoryUsePurpose.RESPONSE_STYLE,
                (MemoryAuthorityLevel.USER_PROVIDED,),
            ),
            _policy(
                task_type,
                MemorySourceType.USER_PREFERENCE,
                MemoryUsePurpose.REPORT_FORMAT_PREFERENCE,
                (MemoryAuthorityLevel.USER_PROVIDED,),
            ),
        ),
        MemoryRetrievalTaskType.DATA_AGENT_SQL: (
            MemoryRetrievalPolicy(
                task_type=task_type,
                allowed_source_types=(MemorySourceType.DATA_AGENT_SQL_CASE,),
                requested_use=MemoryUsePurpose.SQL_GENERATION_GROUNDING,
                min_authority_levels=(MemoryAuthorityLevel.HUMAN_APPROVED,),
                production_context=True,
                max_items=5,
            ),
        ),
        MemoryRetrievalTaskType.SQL_REPAIR: (
            _policy(
                task_type,
                MemorySourceType.DATA_AGENT_SQL_ERROR,
                MemoryUsePurpose.SQL_REPAIR_HINT,
                (
                    MemoryAuthorityLevel.SYSTEM_GENERATED,
                    MemoryAuthorityLevel.UNVERIFIED,
                    MemoryAuthorityLevel.HUMAN_APPROVED,
                ),
                max_items=5,
            ),
            _policy(
                task_type,
                MemorySourceType.DATA_AGENT_SQL_CASE,
                MemoryUsePurpose.SQL_CASE_REFERENCE,
                (MemoryAuthorityLevel.HUMAN_APPROVED,),
                max_items=5,
            ),
        ),
        MemoryRetrievalTaskType.AUDIT_REVIEW: (
            _policy(
                task_type,
                MemorySourceType.AUDIT_EVENT,
                MemoryUsePurpose.AUDIT_REVIEW,
                (MemoryAuthorityLevel.AUDIT_ONLY,),
                max_items=20,
            ),
        ),
        MemoryRetrievalTaskType.EVAL_COLLECTION: (
            _policy(
                task_type,
                MemorySourceType.EVAL_CASE,
                MemoryUsePurpose.EVAL_CANDIDATE,
                (
                    MemoryAuthorityLevel.SYSTEM_GENERATED,
                    MemoryAuthorityLevel.UNVERIFIED,
                    MemoryAuthorityLevel.EVIDENCE_GROUNDED,
                    MemoryAuthorityLevel.HUMAN_APPROVED,
                ),
                max_items=20,
            ),
            _policy(
                task_type,
                MemorySourceType.DATA_AGENT_SQL_ERROR,
                MemoryUsePurpose.EVAL_CANDIDATE,
                (
                    MemoryAuthorityLevel.SYSTEM_GENERATED,
                    MemoryAuthorityLevel.UNVERIFIED,
                ),
                max_items=20,
            ),
            _policy(
                task_type,
                MemorySourceType.RISK_QA_ANSWER,
                MemoryUsePurpose.EVAL_CANDIDATE,
                (
                    MemoryAuthorityLevel.EVIDENCE_GROUNDED,
                    MemoryAuthorityLevel.UNVERIFIED,
                ),
                max_items=20,
            ),
        ),
    }
    return policies[task_type]


def _policy(
    task_type: MemoryRetrievalTaskType,
    source_type: MemorySourceType,
    requested_use: MemoryUsePurpose,
    min_authority_levels: tuple[MemoryAuthorityLevel, ...],
    *,
    max_items: int = 8,
) -> MemoryRetrievalPolicy:
    return MemoryRetrievalPolicy(
        task_type=task_type,
        allowed_source_types=(source_type,),
        requested_use=requested_use,
        min_authority_levels=min_authority_levels,
        max_items=max_items,
    )

