from __future__ import annotations

import pytest

from app.services.memory.adapters import (
    approved_sql_to_memory_candidate,
    failed_sql_to_memory_candidate,
    profile_snapshot_to_memory_candidate,
    risk_qa_answer_to_memory_candidate,
)
from app.services.memory.candidates import MemoryCandidate
from app.services.memory.contracts import (
    MemoryAuthorityLevel,
    MemorySourceType,
    MemoryUsePurpose,
)
from app.services.memory.isolation import validate_memory_use
from app.services.memory.policy import (
    AUDIT_EVENT_ALLOWED,
    AUDIT_EVENT_FORBIDDEN,
    PROFILE_RESULT_ALLOWED,
    PROFILE_RESULT_FORBIDDEN,
    USER_PREFERENCE_ALLOWED,
    USER_PREFERENCE_FORBIDDEN,
)
from app.services.profile_dag.contracts import ProfileNodeRun, ProfileRun, ProfileRunResultSnapshot, utcnow
from app.services.profile_dag.memory_snapshot import build_profile_memory_snapshot


def _node_run(node_key: str, status: str) -> ProfileNodeRun:
    now = utcnow()
    return ProfileNodeRun(
        node_run_id=f"pnr_{node_key}",
        profile_run_id="pr_test",
        uid="U1",
        node_key=node_key,
        skill_name=f"{node_key}_skill",
        stage=0,
        depends_on=[],
        upstream_node_run_ids=[],
        status=status,
        attempt=1,
        started_at=now,
        finished_at=now,
        result_status="ok" if status in {"completed", "degraded"} else "failed",
    )


def _profile_run() -> ProfileRun:
    now = utcnow()
    return ProfileRun(
        run_id="pr_test",
        source="test",
        uids=["U1"],
        requested_modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
        country_code="mx",
        application_time="2026-04-15T12:00:00",
        strict_data_mode=True,
        status="completed_with_degradation",
        trace_id=None,
        session_id=None,
        turn_id=None,
        request_id=None,
        created_at=now,
        started_at=now,
        finished_at=now,
    )


def _profile_snapshot() -> dict[str, object]:
    snapshot = ProfileRunResultSnapshot(
        uid="U1",
        requested_modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
        module_outputs={
            "comprehensive": {
                "summary": "stable summary",
                "structured_result": {
                    "uid": "U1",
                    "status": "ok",
                    "summary": "stable summary",
                    "segment": "S2",
                    "overall_risk": "medium",
                    "overall_value": "high",
                    "confidence": "medium",
                    "metrics": {
                        "segment": "S2",
                        "overall_risk": "medium",
                        "overall_value": "high",
                        "confidence": "medium",
                    },
                },
                "charts": [],
                "report_markdown": "",
            },
        },
        node_runs=[_node_run("comprehensive", "completed")],
    )
    return build_profile_memory_snapshot(_profile_run(), snapshot)


def _user_preference_candidate() -> MemoryCandidate:
    return MemoryCandidate(
        content="User prefers concise Chinese output.",
        memory_source_type=MemorySourceType.USER_PREFERENCE,
        authority_level=MemoryAuthorityLevel.USER_PROVIDED,
        allowed_memory_use=USER_PREFERENCE_ALLOWED,
        forbidden_memory_use=USER_PREFERENCE_FORBIDDEN,
        user_id="u1",
    )


def _audit_event_candidate() -> MemoryCandidate:
    return MemoryCandidate(
        content="Audit trail for SQL approval review.",
        memory_source_type=MemorySourceType.AUDIT_EVENT,
        authority_level=MemoryAuthorityLevel.AUDIT_ONLY,
        allowed_memory_use=AUDIT_EVENT_ALLOWED,
        forbidden_memory_use=AUDIT_EVENT_FORBIDDEN,
        user_id="u1",
    )


def test_profile_result_is_blocked_for_data_agent_field_grounding() -> None:
    candidate = profile_snapshot_to_memory_candidate(_profile_snapshot())

    decision = validate_memory_use(candidate, MemoryUsePurpose.DATA_AGENT_FIELD_GROUNDING)

    assert decision.allowed is False
    assert decision.blocked_by == "explicit_forbidden_use"


def test_profile_result_is_blocked_for_sql_generation_grounding() -> None:
    candidate = profile_snapshot_to_memory_candidate(_profile_snapshot())

    decision = validate_memory_use(candidate, MemoryUsePurpose.SQL_GENERATION_GROUNDING)

    assert decision.allowed is False
    assert decision.blocked_by == "explicit_forbidden_use"


def test_profile_result_is_blocked_for_risk_knowledge_document_evidence() -> None:
    candidate = profile_snapshot_to_memory_candidate(_profile_snapshot())

    decision = validate_memory_use(candidate, MemoryUsePurpose.RISK_KNOWLEDGE_DOCUMENT_EVIDENCE)

    assert decision.allowed is False
    assert decision.blocked_by == "explicit_forbidden_use"


def test_profile_result_is_allowed_for_profile_followup_context() -> None:
    candidate = profile_snapshot_to_memory_candidate(_profile_snapshot())

    decision = validate_memory_use(candidate, MemoryUsePurpose.PROFILE_FOLLOWUP_CONTEXT)

    assert decision.allowed is True
    assert decision.blocked_by is None


def test_risk_qa_answer_is_blocked_for_source_document() -> None:
    candidate = risk_qa_answer_to_memory_candidate(
        answer="Decline due to debt pressure.",
        question="Why was the user rejected?",
        citations=[{"doc_id": "doc-1"}],
        user_id="u1",
    )

    decision = validate_memory_use(candidate, MemoryUsePurpose.RISK_KNOWLEDGE_SOURCE_DOCUMENT)

    assert decision.allowed is False
    assert decision.blocked_by == "explicit_forbidden_use"


def test_risk_qa_answer_is_allowed_for_followup_context() -> None:
    candidate = risk_qa_answer_to_memory_candidate(
        answer="Decline due to debt pressure.",
        question="Why was the user rejected?",
        citations=[{"doc_id": "doc-1"}],
        user_id="u1",
    )

    decision = validate_memory_use(candidate, MemoryUsePurpose.RISK_QA_FOLLOWUP_CONTEXT)

    assert decision.allowed is True


def test_sql_error_is_blocked_for_approved_sql_example() -> None:
    candidate = failed_sql_to_memory_candidate(
        sql="select * from loans",
        error="table not found",
        question="Show all loans",
        user_id="u1",
    )

    decision = validate_memory_use(candidate, MemoryUsePurpose.APPROVED_SQL_EXAMPLE)

    assert decision.allowed is False
    assert decision.blocked_by == "explicit_forbidden_use"


def test_sql_error_is_blocked_for_production_sql_template() -> None:
    candidate = failed_sql_to_memory_candidate(
        sql="select * from loans",
        error="table not found",
        question="Show all loans",
        user_id="u1",
    )

    decision = validate_memory_use(candidate, MemoryUsePurpose.PRODUCTION_SQL_TEMPLATE)

    assert decision.allowed is False
    assert decision.blocked_by == "explicit_forbidden_use"


def test_approved_sql_case_is_allowed_for_sql_case_reference() -> None:
    candidate = approved_sql_to_memory_candidate(
        sql="select uid from approved_loans",
        question="Show approved users",
        approved_sql_hash="abc123",
        user_id="u1",
    )

    decision = validate_memory_use(candidate, MemoryUsePurpose.SQL_CASE_REFERENCE)

    assert decision.allowed is True


def test_malformed_sql_case_cannot_bypass_human_approved_requirement() -> None:
    candidate = MemoryCandidate(
        content="Query template from system output.",
        memory_source_type=MemorySourceType.DATA_AGENT_SQL_CASE,
        authority_level=MemoryAuthorityLevel.SYSTEM_GENERATED,
        allowed_memory_use=(MemoryUsePurpose.SQL_CASE_REFERENCE, MemoryUsePurpose.SQL_GENERATION_GROUNDING),
        forbidden_memory_use=(MemoryUsePurpose.HITL_BYPASS,),
        user_id="u1",
    )

    decision = validate_memory_use(candidate, MemoryUsePurpose.SQL_GENERATION_GROUNDING)

    assert decision.allowed is False
    assert decision.blocked_by == "authority_level_insufficient"


@pytest.mark.parametrize(
    "requested_use",
    [
        MemoryUsePurpose.SAFETY_POLICY_OVERRIDE,
        MemoryUsePurpose.PERMISSION_OVERRIDE,
        MemoryUsePurpose.HITL_BYPASS,
        MemoryUsePurpose.SQL_VALIDATOR_OVERRIDE,
    ],
)
def test_user_preference_is_blocked_from_safety_overrides(requested_use: MemoryUsePurpose) -> None:
    decision = validate_memory_use(_user_preference_candidate(), requested_use)

    assert decision.allowed is False
    assert decision.blocked_by == "explicit_forbidden_use"


def test_audit_event_is_blocked_from_conversation_context() -> None:
    decision = validate_memory_use(_audit_event_candidate(), MemoryUsePurpose.CONVERSATION_CONTEXT)

    assert decision.allowed is False
    assert decision.blocked_by == "explicit_forbidden_use"


def test_unverified_memory_is_blocked_for_production_grounding_in_production_context() -> None:
    candidate = MemoryCandidate(
        content="Unverified retrieval hint.",
        memory_source_type=MemorySourceType.CONVERSATION,
        authority_level=MemoryAuthorityLevel.UNVERIFIED,
        allowed_memory_use=(MemoryUsePurpose.PRODUCTION_GROUNDING,),
        forbidden_memory_use=(MemoryUsePurpose.HITL_BYPASS,),
        user_id="u1",
    )

    decision = validate_memory_use(
        candidate,
        MemoryUsePurpose.PRODUCTION_GROUNDING,
        production_context=True,
    )

    assert decision.allowed is False
    assert decision.blocked_by == "unverified_production_grounding"


def test_profile_snapshot_adapter_preserves_policy_and_metadata() -> None:
    candidate = profile_snapshot_to_memory_candidate(_profile_snapshot())

    assert candidate.memory_source_type is MemorySourceType.PROFILE_RESULT
    assert candidate.authority_level is MemoryAuthorityLevel.SYSTEM_GENERATED
    assert MemoryUsePurpose.DATA_AGENT_FIELD_GROUNDING in candidate.forbidden_memory_use
    assert MemoryUsePurpose.PROFILE_FOLLOWUP_CONTEXT in candidate.allowed_memory_use
    assert candidate.metadata["segment"] == "S2"
    assert candidate.source_run_id == "pr_test"
    assert all(isinstance(use, MemoryUsePurpose) for use in candidate.allowed_memory_use)
    assert all(isinstance(use, MemoryUsePurpose) for use in candidate.forbidden_memory_use)


def test_memory_candidate_requires_content() -> None:
    with pytest.raises(ValueError, match="memory candidate content is required"):
        MemoryCandidate(
            content="",
            memory_source_type=MemorySourceType.PROFILE_RESULT,
            authority_level=MemoryAuthorityLevel.SYSTEM_GENERATED,
            allowed_memory_use=PROFILE_RESULT_ALLOWED,
            forbidden_memory_use=PROFILE_RESULT_FORBIDDEN,
        )
