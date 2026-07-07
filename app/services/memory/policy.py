"""Default memory-use policy for M4 candidates."""

from __future__ import annotations

from collections.abc import Iterable

from app.services.memory.contracts import MemorySourceType, MemoryUsePurpose


CONVERSATION_ALLOWED = (
    MemoryUsePurpose.CONVERSATION_CONTEXT,
    MemoryUsePurpose.FOLLOWUP_CONTEXT,
)
CONVERSATION_FORBIDDEN = (
    MemoryUsePurpose.DATA_AGENT_FIELD_GROUNDING,
    MemoryUsePurpose.SQL_GENERATION_GROUNDING,
    MemoryUsePurpose.RISK_KNOWLEDGE_SOURCE_DOCUMENT,
)

PROFILE_RESULT_ALLOWED = (
    MemoryUsePurpose.PROFILE_RESULT_RECALL,
    MemoryUsePurpose.PROFILE_FOLLOWUP_CONTEXT,
    MemoryUsePurpose.USER_PROFILE_HISTORY,
)
PROFILE_RESULT_FORBIDDEN = (
    MemoryUsePurpose.DATA_AGENT_FIELD_GROUNDING,
    MemoryUsePurpose.RISK_KNOWLEDGE_DOCUMENT_EVIDENCE,
    MemoryUsePurpose.RISK_KNOWLEDGE_SOURCE_DOCUMENT,
    MemoryUsePurpose.APPROVED_STRATEGY_POLICY,
    MemoryUsePurpose.SQL_GENERATION_GROUNDING,
)

RISK_QA_ALLOWED = (
    MemoryUsePurpose.RISK_QA_FOLLOWUP_CONTEXT,
    MemoryUsePurpose.RISK_QA_HISTORY_RECALL,
    MemoryUsePurpose.FOLLOWUP_CONTEXT,
)
RISK_QA_FORBIDDEN = (
    MemoryUsePurpose.RISK_KNOWLEDGE_SOURCE_DOCUMENT,
    MemoryUsePurpose.DATA_AGENT_FIELD_GROUNDING,
    MemoryUsePurpose.SQL_GENERATION_GROUNDING,
    MemoryUsePurpose.APPROVED_SQL_EXAMPLE,
    MemoryUsePurpose.PRODUCTION_SQL_TEMPLATE,
)

SQL_CASE_ALLOWED = (
    MemoryUsePurpose.SQL_CASE_REFERENCE,
    MemoryUsePurpose.SQL_GENERATION_GROUNDING,
)
SQL_CASE_FORBIDDEN = (
    MemoryUsePurpose.SAFETY_POLICY_OVERRIDE,
    MemoryUsePurpose.PERMISSION_OVERRIDE,
    MemoryUsePurpose.HITL_BYPASS,
)

SQL_ERROR_ALLOWED = (
    MemoryUsePurpose.SQL_REPAIR_HINT,
    MemoryUsePurpose.EVAL_CANDIDATE,
)
SQL_ERROR_FORBIDDEN = (
    MemoryUsePurpose.APPROVED_SQL_EXAMPLE,
    MemoryUsePurpose.PRODUCTION_SQL_TEMPLATE,
    MemoryUsePurpose.SQL_GENERATION_GROUNDING,
    MemoryUsePurpose.HITL_BYPASS,
)

USER_PREFERENCE_ALLOWED = (
    MemoryUsePurpose.RESPONSE_STYLE,
    MemoryUsePurpose.REPORT_FORMAT_PREFERENCE,
    MemoryUsePurpose.CONVERSATION_CONTEXT,
)
USER_PREFERENCE_FORBIDDEN = (
    MemoryUsePurpose.PERMISSION_OVERRIDE,
    MemoryUsePurpose.SAFETY_POLICY_OVERRIDE,
    MemoryUsePurpose.HITL_BYPASS,
    MemoryUsePurpose.SQL_VALIDATOR_OVERRIDE,
    MemoryUsePurpose.RISK_KNOWLEDGE_SOURCE_DOCUMENT,
)

AUDIT_EVENT_ALLOWED = (MemoryUsePurpose.AUDIT_REVIEW,)
AUDIT_EVENT_FORBIDDEN = (
    MemoryUsePurpose.CONVERSATION_CONTEXT,
    MemoryUsePurpose.FOLLOWUP_CONTEXT,
    MemoryUsePurpose.PROFILE_FOLLOWUP_CONTEXT,
    MemoryUsePurpose.RISK_QA_FOLLOWUP_CONTEXT,
    MemoryUsePurpose.SQL_GENERATION_GROUNDING,
    MemoryUsePurpose.PRODUCTION_GROUNDING,
)

EVAL_CASE_ALLOWED = (MemoryUsePurpose.EVAL_CANDIDATE,)
EVAL_CASE_FORBIDDEN = (
    MemoryUsePurpose.SQL_GENERATION_GROUNDING,
    MemoryUsePurpose.PRODUCTION_GROUNDING,
)


DEFAULT_ALLOWED_MEMORY_USE: dict[MemorySourceType, tuple[MemoryUsePurpose, ...]] = {
    MemorySourceType.CONVERSATION: CONVERSATION_ALLOWED,
    MemorySourceType.PROFILE_RESULT: PROFILE_RESULT_ALLOWED,
    MemorySourceType.RISK_QA_ANSWER: RISK_QA_ALLOWED,
    MemorySourceType.DATA_AGENT_SQL_CASE: SQL_CASE_ALLOWED,
    MemorySourceType.DATA_AGENT_SQL_ERROR: SQL_ERROR_ALLOWED,
    MemorySourceType.USER_PREFERENCE: USER_PREFERENCE_ALLOWED,
    MemorySourceType.AUDIT_EVENT: AUDIT_EVENT_ALLOWED,
    MemorySourceType.EVAL_CASE: EVAL_CASE_ALLOWED,
}

DEFAULT_FORBIDDEN_MEMORY_USE: dict[MemorySourceType, tuple[MemoryUsePurpose, ...]] = {
    MemorySourceType.CONVERSATION: CONVERSATION_FORBIDDEN,
    MemorySourceType.PROFILE_RESULT: PROFILE_RESULT_FORBIDDEN,
    MemorySourceType.RISK_QA_ANSWER: RISK_QA_FORBIDDEN,
    MemorySourceType.DATA_AGENT_SQL_CASE: SQL_CASE_FORBIDDEN,
    MemorySourceType.DATA_AGENT_SQL_ERROR: SQL_ERROR_FORBIDDEN,
    MemorySourceType.USER_PREFERENCE: USER_PREFERENCE_FORBIDDEN,
    MemorySourceType.AUDIT_EVENT: AUDIT_EVENT_FORBIDDEN,
    MemorySourceType.EVAL_CASE: EVAL_CASE_FORBIDDEN,
}


def memory_use_values(uses: Iterable[MemoryUsePurpose]) -> list[str]:
    return [use.value for use in uses]


def get_allowed_memory_use(source_type: MemorySourceType) -> tuple[MemoryUsePurpose, ...]:
    return DEFAULT_ALLOWED_MEMORY_USE[source_type]


def get_forbidden_memory_use(source_type: MemorySourceType) -> tuple[MemoryUsePurpose, ...]:
    return DEFAULT_FORBIDDEN_MEMORY_USE[source_type]
