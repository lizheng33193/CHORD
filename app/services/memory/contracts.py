"""Core M4 memory contract types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MemorySourceType(str, Enum):
    CONVERSATION = "conversation"
    PROFILE_RESULT = "profile_result"
    RISK_QA_ANSWER = "risk_qa_answer"
    DATA_AGENT_SQL_CASE = "data_agent_sql_case"
    DATA_AGENT_SQL_ERROR = "data_agent_sql_error"
    USER_PREFERENCE = "user_preference"
    AUDIT_EVENT = "audit_event"
    EVAL_CASE = "eval_case"


class MemoryAuthorityLevel(str, Enum):
    USER_PROVIDED = "user_provided"
    SYSTEM_GENERATED = "system_generated"
    EVIDENCE_GROUNDED = "evidence_grounded"
    HUMAN_APPROVED = "human_approved"
    UNVERIFIED = "unverified"
    AUDIT_ONLY = "audit_only"


class MemoryUsePurpose(str, Enum):
    CONVERSATION_CONTEXT = "conversation_context"
    FOLLOWUP_CONTEXT = "followup_context"
    RESPONSE_STYLE = "response_style"
    REPORT_FORMAT_PREFERENCE = "report_format_preference"
    PROFILE_RESULT_RECALL = "profile_result_recall"
    PROFILE_FOLLOWUP_CONTEXT = "profile_followup_context"
    USER_PROFILE_HISTORY = "user_profile_history"
    RISK_QA_FOLLOWUP_CONTEXT = "risk_qa_followup_context"
    RISK_QA_HISTORY_RECALL = "risk_qa_history_recall"
    RISK_KNOWLEDGE_DOCUMENT_EVIDENCE = "risk_knowledge_document_evidence"
    RISK_KNOWLEDGE_SOURCE_DOCUMENT = "risk_knowledge_source_document"
    DATA_AGENT_FIELD_GROUNDING = "data_agent_field_grounding"
    SQL_GENERATION_GROUNDING = "sql_generation_grounding"
    SQL_CASE_REFERENCE = "sql_case_reference"
    SQL_REPAIR_HINT = "sql_repair_hint"
    APPROVED_SQL_EXAMPLE = "approved_sql_example"
    PRODUCTION_SQL_TEMPLATE = "production_sql_template"
    SAFETY_POLICY_OVERRIDE = "safety_policy_override"
    PERMISSION_OVERRIDE = "permission_override"
    HITL_BYPASS = "hitl_bypass"
    SQL_VALIDATOR_OVERRIDE = "sql_validator_override"
    APPROVED_STRATEGY_POLICY = "approved_strategy_policy"
    AUDIT_REVIEW = "audit_review"
    EVAL_CANDIDATE = "eval_candidate"
    PRODUCTION_GROUNDING = "production_grounding"


@dataclass(frozen=True)
class MemoryUseDecision:
    allowed: bool
    requested_use: MemoryUsePurpose
    memory_source_type: MemorySourceType
    authority_level: MemoryAuthorityLevel
    reason: str
    blocked_by: str | None = None
