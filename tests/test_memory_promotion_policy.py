from __future__ import annotations

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
from app.services.memory.promotion import (
    MemoryPromotionBlockReason,
    MemoryPromotionTarget,
    promotion_request_from_candidate,
    promotion_request_from_retrieved_item,
    validate_memory_promotion,
)
from app.services.memory.retrieval import MemoryRetrievedItem
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
        requested_modules=["app", "behavior", "credit", "comprehensive"],
        country_code="mx",
        application_time="2026-04-15T12:00:00",
        strict_data_mode=True,
        status="completed",
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
        requested_modules=["app", "behavior", "credit", "comprehensive"],
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


def _conversation_candidate() -> MemoryCandidate:
    return MemoryCandidate(
        content="User asked for a shorter explanation in the previous turn.",
        memory_source_type=MemorySourceType.CONVERSATION,
        authority_level=MemoryAuthorityLevel.USER_PROVIDED,
        allowed_memory_use=(MemoryUsePurpose.CONVERSATION_CONTEXT, MemoryUsePurpose.FOLLOWUP_CONTEXT),
        forbidden_memory_use=(MemoryUsePurpose.DATA_AGENT_FIELD_GROUNDING,),
        user_id="u1",
    )


def _user_preference_candidate() -> MemoryCandidate:
    return MemoryCandidate(
        content="User prefers concise Chinese output.",
        memory_source_type=MemorySourceType.USER_PREFERENCE,
        authority_level=MemoryAuthorityLevel.USER_PROVIDED,
        allowed_memory_use=(
            MemoryUsePurpose.RESPONSE_STYLE,
            MemoryUsePurpose.REPORT_FORMAT_PREFERENCE,
            MemoryUsePurpose.CONVERSATION_CONTEXT,
        ),
        forbidden_memory_use=(
            MemoryUsePurpose.PERMISSION_OVERRIDE,
            MemoryUsePurpose.SAFETY_POLICY_OVERRIDE,
            MemoryUsePurpose.HITL_BYPASS,
            MemoryUsePurpose.SQL_VALIDATOR_OVERRIDE,
            MemoryUsePurpose.RISK_KNOWLEDGE_SOURCE_DOCUMENT,
        ),
        user_id="u1",
    )


def _audit_event_candidate() -> MemoryCandidate:
    return MemoryCandidate(
        content="Audit trail for SQL approval review.",
        memory_source_type=MemorySourceType.AUDIT_EVENT,
        authority_level=MemoryAuthorityLevel.AUDIT_ONLY,
        allowed_memory_use=(MemoryUsePurpose.AUDIT_REVIEW,),
        forbidden_memory_use=(
            MemoryUsePurpose.CONVERSATION_CONTEXT,
            MemoryUsePurpose.FOLLOWUP_CONTEXT,
            MemoryUsePurpose.PROFILE_FOLLOWUP_CONTEXT,
            MemoryUsePurpose.RISK_QA_FOLLOWUP_CONTEXT,
            MemoryUsePurpose.SQL_GENERATION_GROUNDING,
            MemoryUsePurpose.PRODUCTION_GROUNDING,
        ),
        user_id="u1",
    )


def _eval_case_candidate() -> MemoryCandidate:
    return MemoryCandidate(
        content="Evaluation case for reasoning regression.",
        memory_source_type=MemorySourceType.EVAL_CASE,
        authority_level=MemoryAuthorityLevel.SYSTEM_GENERATED,
        allowed_memory_use=(MemoryUsePurpose.EVAL_CANDIDATE,),
        forbidden_memory_use=(
            MemoryUsePurpose.SQL_GENERATION_GROUNDING,
            MemoryUsePurpose.PRODUCTION_GROUNDING,
        ),
        user_id="u1",
    )


def _retrieved_item() -> MemoryRetrievedItem:
    candidate = approved_sql_to_memory_candidate(
        sql="select uid from approved_loans",
        question="Show approved users",
        approved_sql_hash="abc123",
        user_id="u1",
        project_id="p1",
        country="mx",
        source_run_id="run-sql",
    )
    return MemoryRetrievedItem(
        memory_id="memory-1",
        content=candidate.content,
        memory_source_type=candidate.memory_source_type,
        authority_level=candidate.authority_level,
        allowed_memory_use=candidate.allowed_memory_use,
        forbidden_memory_use=candidate.forbidden_memory_use,
        requested_use=MemoryUsePurpose.SQL_CASE_REFERENCE,
        use_decision=None,  # type: ignore[arg-type]
        evidence_status=candidate.evidence_status,
        source_run_id=candidate.source_run_id,
        source_artifact_id=candidate.source_artifact_id,
        score=0.9,
        metadata=dict(candidate.metadata),
    )


def test_approved_sql_example_requires_human_approved_case_and_hash() -> None:
    candidate = approved_sql_to_memory_candidate(
        sql="select uid from approved_loans",
        question="Show approved users",
        approved_sql_hash="abc123",
        user_id="u1",
    )

    decision = validate_memory_promotion(
        promotion_request_from_candidate(candidate, MemoryPromotionTarget.APPROVED_SQL_EXAMPLE)
    )

    assert decision.allowed is True
    assert "requires governance ingestion" in decision.reason


def test_approved_sql_example_blocks_missing_hash() -> None:
    candidate = MemoryCandidate(
        content="Approved SQL case without hash.",
        memory_source_type=MemorySourceType.DATA_AGENT_SQL_CASE,
        authority_level=MemoryAuthorityLevel.HUMAN_APPROVED,
        allowed_memory_use=(MemoryUsePurpose.SQL_CASE_REFERENCE,),
        forbidden_memory_use=(MemoryUsePurpose.HITL_BYPASS,),
        user_id="u1",
        metadata={"question": "Show approved users"},
    )

    decision = validate_memory_promotion(
        promotion_request_from_candidate(candidate, MemoryPromotionTarget.APPROVED_SQL_EXAMPLE)
    )

    assert decision.allowed is False
    assert decision.blocked_by is MemoryPromotionBlockReason.EVIDENCE_INSUFFICIENT


def test_approved_sql_example_blocks_insufficient_authority() -> None:
    candidate = MemoryCandidate(
        content="System generated SQL draft.",
        memory_source_type=MemorySourceType.DATA_AGENT_SQL_CASE,
        authority_level=MemoryAuthorityLevel.SYSTEM_GENERATED,
        allowed_memory_use=(MemoryUsePurpose.SQL_CASE_REFERENCE,),
        forbidden_memory_use=(MemoryUsePurpose.HITL_BYPASS,),
        user_id="u1",
        metadata={"approved_sql_hash": "abc123"},
    )

    decision = validate_memory_promotion(
        promotion_request_from_candidate(candidate, MemoryPromotionTarget.APPROVED_SQL_EXAMPLE)
    )

    assert decision.allowed is False
    assert decision.blocked_by is MemoryPromotionBlockReason.AUTHORITY_LEVEL_INSUFFICIENT


def test_sql_case_allows_human_approved_sql_case() -> None:
    candidate = approved_sql_to_memory_candidate(
        sql="select uid from approved_loans",
        question="Show approved users",
        approved_sql_hash="abc123",
        user_id="u1",
    )

    decision = validate_memory_promotion(
        promotion_request_from_candidate(candidate, MemoryPromotionTarget.SQL_CASE)
    )

    assert decision.allowed is True


def test_sql_error_is_blocked_for_approved_sql_example() -> None:
    candidate = failed_sql_to_memory_candidate(
        sql="select * from loans",
        error="table not found",
        question="Show all loans",
        user_id="u1",
    )

    decision = validate_memory_promotion(
        promotion_request_from_candidate(candidate, MemoryPromotionTarget.APPROVED_SQL_EXAMPLE)
    )

    assert decision.allowed is False
    assert decision.blocked_by is MemoryPromotionBlockReason.EXPLICITLY_FORBIDDEN


def test_sql_error_is_allowed_for_sql_error_case_and_eval_candidate() -> None:
    candidate = failed_sql_to_memory_candidate(
        sql="select * from loans",
        error="table not found",
        question="Show all loans",
        user_id="u1",
    )

    error_case = validate_memory_promotion(
        promotion_request_from_candidate(candidate, MemoryPromotionTarget.SQL_ERROR_CASE)
    )
    eval_case = validate_memory_promotion(
        promotion_request_from_candidate(candidate, MemoryPromotionTarget.EVAL_CANDIDATE)
    )

    assert error_case.allowed is True
    assert eval_case.allowed is True


def test_risk_qa_answer_requires_grounding_for_eval_candidate() -> None:
    grounded = risk_qa_answer_to_memory_candidate(
        answer="Decline due to debt pressure.",
        question="Why was the user rejected?",
        citations=[{"doc_id": "doc-1"}],
        user_id="u1",
    )
    unverified = risk_qa_answer_to_memory_candidate(
        answer="Maybe due to debt pressure.",
        question="Why was the user rejected?",
        citations=None,
        user_id="u1",
    )

    grounded_decision = validate_memory_promotion(
        promotion_request_from_candidate(grounded, MemoryPromotionTarget.EVAL_CANDIDATE)
    )
    unverified_decision = validate_memory_promotion(
        promotion_request_from_candidate(unverified, MemoryPromotionTarget.EVAL_CANDIDATE)
    )

    assert grounded_decision.allowed is True
    assert unverified_decision.allowed is False
    assert unverified_decision.blocked_by is MemoryPromotionBlockReason.AUTHORITY_LEVEL_INSUFFICIENT


def test_risk_qa_answer_allows_history_but_blocks_knowledge_source() -> None:
    candidate = risk_qa_answer_to_memory_candidate(
        answer="Decline due to debt pressure.",
        question="Why was the user rejected?",
        citations=[{"doc_id": "doc-1"}],
        user_id="u1",
    )

    history = validate_memory_promotion(
        promotion_request_from_candidate(candidate, MemoryPromotionTarget.RISK_QA_HISTORY)
    )
    source_doc = validate_memory_promotion(
        promotion_request_from_candidate(candidate, MemoryPromotionTarget.RISK_KNOWLEDGE_SOURCE_DOCUMENT)
    )

    assert history.allowed is True
    assert source_doc.allowed is False
    assert source_doc.blocked_by is MemoryPromotionBlockReason.EXPLICITLY_FORBIDDEN


def test_profile_result_allows_history_but_blocks_authority_and_strategy() -> None:
    candidate = profile_snapshot_to_memory_candidate(_profile_snapshot())

    history = validate_memory_promotion(
        promotion_request_from_candidate(candidate, MemoryPromotionTarget.PROFILE_HISTORY)
    )
    data_authority = validate_memory_promotion(
        promotion_request_from_candidate(candidate, MemoryPromotionTarget.DATA_KNOWLEDGE_AUTHORITY)
    )
    strategy = validate_memory_promotion(
        promotion_request_from_candidate(candidate, MemoryPromotionTarget.APPROVED_STRATEGY_POLICY)
    )

    assert history.allowed is True
    assert data_authority.allowed is False
    assert data_authority.blocked_by is MemoryPromotionBlockReason.EXPLICITLY_FORBIDDEN
    assert strategy.allowed is False
    assert strategy.blocked_by is MemoryPromotionBlockReason.EXPLICITLY_FORBIDDEN


def test_user_preference_blocks_safety_and_hitl_targets() -> None:
    candidate = _user_preference_candidate()

    safety = validate_memory_promotion(
        promotion_request_from_candidate(candidate, MemoryPromotionTarget.SAFETY_POLICY)
    )
    hitl = validate_memory_promotion(
        promotion_request_from_candidate(candidate, MemoryPromotionTarget.HITL_BYPASS_POLICY)
    )

    assert safety.allowed is False
    assert safety.blocked_by is MemoryPromotionBlockReason.EXPLICITLY_FORBIDDEN
    assert hitl.allowed is False
    assert hitl.blocked_by is MemoryPromotionBlockReason.EXPLICITLY_FORBIDDEN


def test_conversation_blocks_data_authority() -> None:
    decision = validate_memory_promotion(
        promotion_request_from_candidate(_conversation_candidate(), MemoryPromotionTarget.DATA_KNOWLEDGE_AUTHORITY)
    )

    assert decision.allowed is False
    assert decision.blocked_by is MemoryPromotionBlockReason.EXPLICITLY_FORBIDDEN


def test_audit_event_allows_eval_candidate_only() -> None:
    candidate = _audit_event_candidate()

    eval_decision = validate_memory_promotion(
        promotion_request_from_candidate(candidate, MemoryPromotionTarget.EVAL_CANDIDATE)
    )
    source_doc = validate_memory_promotion(
        promotion_request_from_candidate(candidate, MemoryPromotionTarget.RISK_KNOWLEDGE_SOURCE_DOCUMENT)
    )

    assert eval_decision.allowed is True
    assert "candidate only" in eval_decision.reason
    assert source_doc.allowed is False
    assert source_doc.blocked_by is MemoryPromotionBlockReason.EXPLICITLY_FORBIDDEN


def test_eval_case_allows_eval_candidate() -> None:
    decision = validate_memory_promotion(
        promotion_request_from_candidate(_eval_case_candidate(), MemoryPromotionTarget.EVAL_CANDIDATE)
    )

    assert decision.allowed is True


def test_promotion_request_helpers_preserve_candidate_and_retrieval_fields() -> None:
    candidate = approved_sql_to_memory_candidate(
        sql="select uid from approved_loans",
        question="Show approved users",
        approved_sql_hash="abc123",
        user_id="u1",
        project_id="p1",
        country="mx",
        source_run_id="run-sql",
    )

    request = promotion_request_from_candidate(candidate, MemoryPromotionTarget.APPROVED_SQL_EXAMPLE)
    retrieved_request = promotion_request_from_retrieved_item(
        _retrieved_item(),
        MemoryPromotionTarget.APPROVED_SQL_EXAMPLE,
    )

    assert request.memory_source_type is MemorySourceType.DATA_AGENT_SQL_CASE
    assert request.authority_level is MemoryAuthorityLevel.HUMAN_APPROVED
    assert request.allowed_memory_use == candidate.allowed_memory_use
    assert request.forbidden_memory_use == candidate.forbidden_memory_use
    assert request.source_run_id == "run-sql"
    assert request.source_artifact_id == "abc123"
    assert request.metadata["approved_sql_hash"] == "abc123"

    assert retrieved_request.memory_source_type is MemorySourceType.DATA_AGENT_SQL_CASE
    assert retrieved_request.authority_level is MemoryAuthorityLevel.HUMAN_APPROVED
    assert retrieved_request.source_memory_id == "memory-1"
    assert retrieved_request.source_artifact_id == "abc123"
    assert retrieved_request.metadata["approved_sql_hash"] == "abc123"
