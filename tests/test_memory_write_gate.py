from __future__ import annotations

from typing import Any

import pytest

from app.services.memory.adapters import (
    approved_sql_to_memory_candidate,
    failed_sql_to_memory_candidate,
    profile_snapshot_to_memory_candidate,
)
from app.services.memory.contracts import MemoryUsePurpose
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
        requested_modules=["comprehensive"],
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
        requested_modules=["comprehensive"],
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


def _profile_candidate():
    return profile_snapshot_to_memory_candidate(_profile_snapshot(), user_id="u1", project_id="p1", country="mx")


class _MalformedCandidate:
    content = "valid content"


class _EmptyFakeCandidate:
    content = "   "
    memory_source_type = "profile_result"
    authority_level = "system_generated"
    allowed_memory_use = ("profile_result_recall",)
    forbidden_memory_use = ("sql_generation_grounding",)
    user_id = "u1"
    project_id = "p1"
    country = "mx"
    session_id = None
    source_run_id = None
    source_artifact_id = None
    evidence_status = None
    importance = 0.5
    confidence = 0.5
    metadata: dict[str, Any] = {}


def test_evaluate_accepts_valid_profile_candidate() -> None:
    from app.services.memory.records import MemoryWriteStatus
    from app.services.memory.write_gate import MemoryWriteGate

    decision = MemoryWriteGate().evaluate(_profile_candidate())

    assert decision.status is MemoryWriteStatus.ACCEPTED
    assert decision.accepted is True
    assert decision.persisted is False
    assert decision.record_draft is not None
    assert decision.record_draft.memory_source_type == "profile_result"
    assert decision.record_draft.authority_level == "system_generated"
    assert decision.record_draft.allowed_memory_use == [
        MemoryUsePurpose.PROFILE_RESULT_RECALL.value,
        MemoryUsePurpose.PROFILE_FOLLOWUP_CONTEXT.value,
        MemoryUsePurpose.USER_PROFILE_HISTORY.value,
    ]
    assert decision.record_draft.metadata_json["write_gate"]["status"] == decision.status.value
    assert decision.record_draft.metadata_json["write_gate"]["dedupe_key"] == decision.dedupe_key


def test_evaluate_never_returns_deferred() -> None:
    from app.services.memory.records import MemoryWriteStatus
    from app.services.memory.write_gate import MemoryWriteGate

    decision = MemoryWriteGate().evaluate(_profile_candidate())

    assert decision.status is not MemoryWriteStatus.DEFERRED


def test_write_returns_deferred_when_store_write_disabled() -> None:
    from app.services.memory.records import MemoryWriteStatus
    from app.services.memory.write_gate import MemoryWriteGate

    decision = MemoryWriteGate(allow_store_write=False).write(_profile_candidate())

    assert decision.status is MemoryWriteStatus.DEFERRED
    assert decision.accepted is True
    assert decision.persisted is False
    assert decision.memory_id is None
    assert decision.record_draft is not None


def test_evaluate_rejects_invalid_candidate_shape() -> None:
    from app.services.memory.records import MemoryWriteRejectReason, MemoryWriteStatus
    from app.services.memory.write_gate import MemoryWriteGate

    decision = MemoryWriteGate().evaluate(_MalformedCandidate())

    assert decision.status is MemoryWriteStatus.REJECTED
    assert decision.reject_reason is MemoryWriteRejectReason.INVALID_CANDIDATE


def test_evaluate_rejects_empty_content_from_malformed_candidate() -> None:
    from app.services.memory.records import MemoryWriteRejectReason, MemoryWriteStatus
    from app.services.memory.write_gate import MemoryWriteGate

    decision = MemoryWriteGate().evaluate(_EmptyFakeCandidate())

    assert decision.status is MemoryWriteStatus.REJECTED
    assert decision.reject_reason is MemoryWriteRejectReason.EMPTY_CONTENT


def test_evaluate_rejects_missing_user_scope_when_required() -> None:
    from app.services.memory.records import MemoryWriteRejectReason, MemoryWriteStatus
    from app.services.memory.write_gate import MemoryWriteGate

    candidate = profile_snapshot_to_memory_candidate(_profile_snapshot(), project_id="p1", country="mx")

    decision = MemoryWriteGate(require_scope=True).evaluate(candidate)

    assert decision.status is MemoryWriteStatus.REJECTED
    assert decision.reject_reason is MemoryWriteRejectReason.MISSING_SCOPE


@pytest.mark.parametrize(
    "content",
    [
        "password=supersecret123",
        "token=abc12345678",
        "api_key=xyz12345678",
        "sk-abc12345XYZ9876",
        "Bearer ABCD1234token",
        "-----BEGIN PRIVATE KEY-----",
    ],
)
def test_evaluate_rejects_hard_secret_patterns(content: str) -> None:
    from app.services.memory.records import MemoryWriteRejectReason, MemoryWriteStatus
    from app.services.memory.write_gate import MemoryWriteGate

    candidate = _profile_candidate()
    candidate = type(candidate)(
        content=content,
        memory_source_type=candidate.memory_source_type,
        authority_level=candidate.authority_level,
        allowed_memory_use=candidate.allowed_memory_use,
        forbidden_memory_use=candidate.forbidden_memory_use,
        user_id=candidate.user_id,
        project_id=candidate.project_id,
        country=candidate.country,
        session_id=candidate.session_id,
        source_run_id=candidate.source_run_id,
        source_artifact_id=candidate.source_artifact_id,
        evidence_status=candidate.evidence_status,
        importance=candidate.importance,
        confidence=candidate.confidence,
        metadata=candidate.metadata,
    )

    decision = MemoryWriteGate().evaluate(candidate)

    assert decision.status is MemoryWriteStatus.REJECTED
    assert decision.reject_reason is MemoryWriteRejectReason.SECRET_DETECTED


def test_dedupe_key_is_stable_across_whitespace_and_case() -> None:
    from app.services.memory.candidates import MemoryCandidate
    from app.services.memory.contracts import MemoryAuthorityLevel, MemorySourceType
    from app.services.memory.dedupe import build_memory_dedupe_key

    candidate_a = MemoryCandidate(
        content="Profile result for UID 123",
        memory_source_type=MemorySourceType.PROFILE_RESULT,
        authority_level=MemoryAuthorityLevel.SYSTEM_GENERATED,
        allowed_memory_use=_profile_candidate().allowed_memory_use,
        forbidden_memory_use=_profile_candidate().forbidden_memory_use,
        user_id="u1",
        project_id="p1",
        country="mx",
    )
    candidate_b = MemoryCandidate(
        content=" profile   result FOR uid 123 ",
        memory_source_type=MemorySourceType.PROFILE_RESULT,
        authority_level=MemoryAuthorityLevel.SYSTEM_GENERATED,
        allowed_memory_use=_profile_candidate().allowed_memory_use,
        forbidden_memory_use=_profile_candidate().forbidden_memory_use,
        user_id="u1",
        project_id="p1",
        country="mx",
    )

    assert build_memory_dedupe_key(candidate_a) == build_memory_dedupe_key(candidate_b)


def test_duplicate_candidate_is_skipped_in_memory_adapter() -> None:
    from app.services.memory.records import MemoryWriteStatus
    from app.services.memory.store_adapter import InMemoryMemoryStoreAdapter
    from app.services.memory.write_gate import MemoryWriteGate

    store = InMemoryMemoryStoreAdapter()
    gate = MemoryWriteGate(store=store, allow_store_write=True)

    first = gate.write(_profile_candidate())
    second = gate.write(_profile_candidate())

    assert first.status is MemoryWriteStatus.ACCEPTED
    assert first.memory_id is not None
    assert second.status is MemoryWriteStatus.SKIPPED_DUPLICATE
    assert second.accepted is False


def test_failed_sql_candidate_preserves_error_metadata() -> None:
    from app.services.memory.write_gate import MemoryWriteGate

    decision = MemoryWriteGate().evaluate(
        failed_sql_to_memory_candidate(
            sql="select * from loans",
            error="table not found",
            question="Show all loans",
            user_id="u1",
            project_id="p1",
            country="mx",
            source_run_id="run-1",
        )
    )

    assert decision.record_draft is not None
    assert decision.record_draft.memory_source_type == "data_agent_sql_error"
    assert "approved_sql_example" in decision.record_draft.forbidden_memory_use
    assert decision.record_draft.metadata_json["candidate_metadata"]["error"] == "table not found"


def test_approved_sql_candidate_preserves_hash_and_authority() -> None:
    from app.services.memory.write_gate import MemoryWriteGate

    decision = MemoryWriteGate().evaluate(
        approved_sql_to_memory_candidate(
            sql="select uid from approved_loans",
            question="Show approved users",
            approved_sql_hash="abc123",
            user_id="u1",
            project_id="p1",
            country="mx",
            source_run_id="run-1",
        )
    )

    assert decision.record_draft is not None
    assert decision.record_draft.memory_source_type == "data_agent_sql_case"
    assert decision.record_draft.authority_level == "human_approved"
    assert "sql_case_reference" in decision.record_draft.allowed_memory_use
    assert decision.record_draft.metadata_json["candidate_metadata"]["approved_sql_hash"] == "abc123"
