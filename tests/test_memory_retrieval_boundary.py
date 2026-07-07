from __future__ import annotations

import pytest

from app.services.memory.contracts import (
    MemoryAuthorityLevel,
    MemorySourceType,
    MemoryUsePurpose,
)
from app.services.orchestrator_agent.memory_store import MemoryRecord, SQLiteMemoryStore


def _record(
    *,
    memory_id: str,
    content: str,
    source_type: MemorySourceType,
    authority: MemoryAuthorityLevel,
    allowed: tuple[MemoryUsePurpose, ...],
    forbidden: tuple[MemoryUsePurpose, ...] = (MemoryUsePurpose.PERMISSION_OVERRIDE,),
    user_id: str = "u1",
    project_id: str | None = "p1",
    country: str | None = "mx",
    status: str = "active",
    importance: float = 0.5,
    confidence: float = 0.5,
    created_at: str = "2026-07-07T00:00:00+00:00",
):
    from app.services.memory.retrieval_adapter import MemoryStoredRecord

    metadata_json = {
        "m4_contract_version": "m4-2",
        "memory_source_type": source_type.value,
        "authority_level": authority.value,
        "allowed_memory_use": [item.value for item in allowed],
        "forbidden_memory_use": [item.value for item in forbidden],
        "source_run_id": f"run-{memory_id}",
        "source_artifact_id": f"artifact-{memory_id}",
        "evidence_status": "grounded" if authority is MemoryAuthorityLevel.EVIDENCE_GROUNDED else None,
        "candidate_metadata": {"label": memory_id},
        "scope_warnings": [],
        "write_gate": {
            "status": "accepted",
            "reject_reason": None,
            "redacted": False,
            "dedupe_key": f"dedupe-{memory_id}",
            "decision_reason": "accepted",
        },
    }
    return MemoryStoredRecord(
        memory_id=memory_id,
        content=content,
        user_id=user_id,
        project_id=project_id,
        country=country,
        status=status,
        metadata_json=metadata_json,
        importance=importance,
        confidence=confidence,
        created_at=created_at,
    )


def _service_with_records(*records):
    from app.services.memory.retrieval import MemoryRetrievalService
    from app.services.memory.retrieval_adapter import InMemoryMemoryRetrievalAdapter

    return MemoryRetrievalService(InMemoryMemoryRetrievalAdapter(records=list(records)))


def test_profile_followup_retrieves_profile_result_and_preference_with_split_use() -> None:
    from app.services.memory.retrieval import MemoryRetrievalRequest
    from app.services.memory.retrieval_policy import MemoryRetrievalTaskType

    service = _service_with_records(
        _record(
            memory_id="profile-1",
            content="Profile result for uid=U1: segment=S2.",
            source_type=MemorySourceType.PROFILE_RESULT,
            authority=MemoryAuthorityLevel.SYSTEM_GENERATED,
            allowed=(MemoryUsePurpose.PROFILE_FOLLOWUP_CONTEXT,),
        ),
        _record(
            memory_id="pref-1",
            content="User prefers concise Chinese output.",
            source_type=MemorySourceType.USER_PREFERENCE,
            authority=MemoryAuthorityLevel.USER_PROVIDED,
            allowed=(
                MemoryUsePurpose.RESPONSE_STYLE,
                MemoryUsePurpose.REPORT_FORMAT_PREFERENCE,
            ),
        ),
    )

    result = service.retrieve(
        MemoryRetrievalRequest(
            query="follow up on this profile",
            task_type=MemoryRetrievalTaskType.PROFILE_FOLLOWUP,
            user_id="u1",
            project_id="p1",
            country="mx",
        )
    )

    assert {item.memory_source_type for item in result.items} == {
        MemorySourceType.PROFILE_RESULT,
        MemorySourceType.USER_PREFERENCE,
    }
    profile_item = next(item for item in result.items if item.memory_source_type is MemorySourceType.PROFILE_RESULT)
    preference_item = next(item for item in result.items if item.memory_source_type is MemorySourceType.USER_PREFERENCE)
    assert profile_item.requested_use is MemoryUsePurpose.PROFILE_FOLLOWUP_CONTEXT
    assert preference_item.requested_use in {
        MemoryUsePurpose.RESPONSE_STYLE,
        MemoryUsePurpose.REPORT_FORMAT_PREFERENCE,
    }


def test_risk_qa_followup_retrieves_risk_answer() -> None:
    from app.services.memory.retrieval import MemoryRetrievalRequest
    from app.services.memory.retrieval_policy import MemoryRetrievalTaskType

    service = _service_with_records(
        _record(
            memory_id="risk-1",
            content="Risk QA answer: decline due to debt pressure.",
            source_type=MemorySourceType.RISK_QA_ANSWER,
            authority=MemoryAuthorityLevel.EVIDENCE_GROUNDED,
            allowed=(MemoryUsePurpose.RISK_QA_FOLLOWUP_CONTEXT,),
        )
    )

    result = service.retrieve(
        MemoryRetrievalRequest(
            query="why was the user rejected?",
            task_type=MemoryRetrievalTaskType.RISK_QA_FOLLOWUP,
            user_id="u1",
            project_id="p1",
            country="mx",
        )
    )

    assert len(result.items) == 1
    assert result.items[0].memory_source_type is MemorySourceType.RISK_QA_ANSWER
    assert result.items[0].requested_use is MemoryUsePurpose.RISK_QA_FOLLOWUP_CONTEXT


def test_data_agent_sql_does_not_return_profile_result() -> None:
    from app.services.memory.retrieval import MemoryRetrievalRequest
    from app.services.memory.retrieval_policy import MemoryRetrievalTaskType

    service = _service_with_records(
        _record(
            memory_id="profile-1",
            content="Profile result for uid=U1: segment=S2.",
            source_type=MemorySourceType.PROFILE_RESULT,
            authority=MemoryAuthorityLevel.SYSTEM_GENERATED,
            allowed=(MemoryUsePurpose.PROFILE_FOLLOWUP_CONTEXT,),
        )
    )

    result = service.retrieve(
        MemoryRetrievalRequest(
            query="show approved users",
            task_type=MemoryRetrievalTaskType.DATA_AGENT_SQL,
            user_id="u1",
            project_id="p1",
            country="mx",
        )
    )

    assert result.items == ()


def test_data_agent_sql_returns_only_human_approved_sql_case() -> None:
    from app.services.memory.retrieval import MemoryRetrievalRequest
    from app.services.memory.retrieval_policy import MemoryRetrievalTaskType

    approved = _record(
        memory_id="sql-ok",
        content="Approved SQL case for approved_loans cohort.",
        source_type=MemorySourceType.DATA_AGENT_SQL_CASE,
        authority=MemoryAuthorityLevel.HUMAN_APPROVED,
        allowed=(MemoryUsePurpose.SQL_GENERATION_GROUNDING,),
        importance=0.9,
    )
    system_generated = _record(
        memory_id="sql-bad",
        content="System-generated SQL draft.",
        source_type=MemorySourceType.DATA_AGENT_SQL_CASE,
        authority=MemoryAuthorityLevel.SYSTEM_GENERATED,
        allowed=(MemoryUsePurpose.SQL_GENERATION_GROUNDING,),
        importance=0.8,
    )
    service = _service_with_records(approved, system_generated)

    result = service.retrieve(
        MemoryRetrievalRequest(
            query="approved loan cohort",
            task_type=MemoryRetrievalTaskType.DATA_AGENT_SQL,
            user_id="u1",
            project_id="p1",
            country="mx",
        )
    )

    assert [item.memory_id for item in result.items] == ["sql-ok"]
    assert [item.memory_id for item in result.rejected_items] == ["sql-bad"]
    assert result.rejected_items[0].blocked_by == "authority_level_insufficient"


def test_sql_error_does_not_enter_data_agent_sql_grounding() -> None:
    from app.services.memory.retrieval import MemoryRetrievalRequest
    from app.services.memory.retrieval_policy import MemoryRetrievalTaskType

    service = _service_with_records(
        _record(
            memory_id="sql-error",
            content="SQL failed because table not found.",
            source_type=MemorySourceType.DATA_AGENT_SQL_ERROR,
            authority=MemoryAuthorityLevel.SYSTEM_GENERATED,
            allowed=(MemoryUsePurpose.SQL_REPAIR_HINT,),
        )
    )

    result = service.retrieve(
        MemoryRetrievalRequest(
            query="generate production sql",
            task_type=MemoryRetrievalTaskType.DATA_AGENT_SQL,
            user_id="u1",
            project_id="p1",
            country="mx",
        )
    )

    assert result.items == ()


def test_sql_repair_retrieves_sql_error_as_repair_hint() -> None:
    from app.services.memory.retrieval import MemoryRetrievalRequest
    from app.services.memory.retrieval_policy import MemoryRetrievalTaskType

    service = _service_with_records(
        _record(
            memory_id="sql-error",
            content="SQL failed because table not found.",
            source_type=MemorySourceType.DATA_AGENT_SQL_ERROR,
            authority=MemoryAuthorityLevel.SYSTEM_GENERATED,
            allowed=(MemoryUsePurpose.SQL_REPAIR_HINT,),
        )
    )

    result = service.retrieve(
        MemoryRetrievalRequest(
            query="repair this broken sql",
            task_type=MemoryRetrievalTaskType.SQL_REPAIR,
            user_id="u1",
            project_id="p1",
            country="mx",
        )
    )

    assert len(result.items) == 1
    assert result.items[0].memory_id == "sql-error"
    assert result.items[0].requested_use is MemoryUsePurpose.SQL_REPAIR_HINT


def test_audit_event_appears_only_for_audit_review() -> None:
    from app.services.memory.retrieval import MemoryRetrievalRequest
    from app.services.memory.retrieval_policy import MemoryRetrievalTaskType

    record = _record(
        memory_id="audit-1",
        content="Audit log for SQL approval.",
        source_type=MemorySourceType.AUDIT_EVENT,
        authority=MemoryAuthorityLevel.AUDIT_ONLY,
        allowed=(MemoryUsePurpose.AUDIT_REVIEW,),
    )
    service = _service_with_records(record)

    general = service.retrieve(
        MemoryRetrievalRequest(
            query="tell me what happened",
            task_type=MemoryRetrievalTaskType.GENERAL_CHAT,
            user_id="u1",
            project_id="p1",
            country="mx",
        )
    )
    audit = service.retrieve(
        MemoryRetrievalRequest(
            query="review this audit event",
            task_type=MemoryRetrievalTaskType.AUDIT_REVIEW,
            user_id="u1",
            project_id="p1",
            country="mx",
        )
    )

    assert general.items == ()
    assert [item.memory_id for item in audit.items] == ["audit-1"]


def test_malformed_m4_metadata_is_rejected() -> None:
    from app.services.memory.retrieval import MemoryRetrievalRequest
    from app.services.memory.retrieval_policy import MemoryRetrievalTaskType
    from app.services.memory.retrieval_adapter import MemoryStoredRecord

    malformed = MemoryStoredRecord(
        memory_id="broken-1",
        content="Broken metadata.",
        user_id="u1",
        project_id="p1",
        country="mx",
        status="active",
        metadata_json={
            "m4_contract_version": "m4-2",
            "memory_source_type": MemorySourceType.USER_PREFERENCE.value,
        },
        created_at="2026-07-07T00:00:00+00:00",
    )
    service = _service_with_records(malformed)

    result = service.retrieve(
        MemoryRetrievalRequest(
            query="reply in Chinese",
            task_type=MemoryRetrievalTaskType.GENERAL_CHAT,
            user_id="u1",
            project_id="p1",
            country="mx",
        )
    )

    assert result.items == ()
    assert [item.memory_id for item in result.rejected_items] == ["broken-1"]
    assert result.rejected_items[0].reason == "malformed_m4_metadata"


def test_request_requires_user_id() -> None:
    from app.services.memory.retrieval import MemoryRetrievalRequest
    from app.services.memory.retrieval_policy import MemoryRetrievalTaskType

    with pytest.raises(ValueError, match="user_id"):
        MemoryRetrievalRequest(
            query="reply in Chinese",
            task_type=MemoryRetrievalTaskType.GENERAL_CHAT,
            user_id="",
        )


def test_request_max_items_is_global_limit_across_policies() -> None:
    from app.services.memory.retrieval import MemoryRetrievalRequest
    from app.services.memory.retrieval_policy import MemoryRetrievalTaskType

    service = _service_with_records(
        _record(
            memory_id="profile-1",
            content="Profile result for uid=U1: segment=S2.",
            source_type=MemorySourceType.PROFILE_RESULT,
            authority=MemoryAuthorityLevel.SYSTEM_GENERATED,
            allowed=(MemoryUsePurpose.PROFILE_FOLLOWUP_CONTEXT,),
            importance=0.95,
        ),
        _record(
            memory_id="conv-1",
            content="Conversation recap: user asked about credit behavior.",
            source_type=MemorySourceType.CONVERSATION,
            authority=MemoryAuthorityLevel.UNVERIFIED,
            allowed=(MemoryUsePurpose.FOLLOWUP_CONTEXT,),
            importance=0.85,
        ),
        _record(
            memory_id="pref-1",
            content="User prefers concise Chinese output.",
            source_type=MemorySourceType.USER_PREFERENCE,
            authority=MemoryAuthorityLevel.USER_PROVIDED,
            allowed=(MemoryUsePurpose.RESPONSE_STYLE,),
            importance=0.75,
        ),
    )

    result = service.retrieve(
        MemoryRetrievalRequest(
            query="follow up",
            task_type=MemoryRetrievalTaskType.PROFILE_FOLLOWUP,
            user_id="u1",
            project_id="p1",
            country="mx",
            max_items=2,
        )
    )

    assert len(result.items) == 2


def test_sqlite_adapter_excludes_legacy_records_when_include_legacy_memory_is_false(tmp_path) -> None:
    from app.services.memory.retrieval import MemoryRetrievalRequest, MemoryRetrievalService
    from app.services.memory.retrieval_adapter import SQLiteV1MemoryRetrievalAdapter
    from app.services.memory.retrieval_policy import MemoryRetrievalTaskType

    db_path = tmp_path / "memory.sqlite3"
    store = SQLiteMemoryStore(db_path)
    store.add(
        MemoryRecord(
            memory_id="legacy-1",
            scope="user",
            user_id="u1",
            project_id="p1",
            session_id=None,
            country="mx",
            category="preference",
            memory_type="semantic",
            content="Legacy memory without M4 metadata.",
            source="memory_tool",
            dedupe_key="legacy-1",
            metadata={"legacy_only": True},
        )
    )
    store.add(
        MemoryRecord(
            memory_id="m4-1",
            scope="user",
            user_id="u1",
            project_id="p1",
            session_id=None,
            country="mx",
            category="preference",
            memory_type="semantic",
            content="User prefers concise Chinese output.",
            source="m4_write_gate",
            dedupe_key="m4-1",
            metadata=_record(
                memory_id="m4-1",
                content="User prefers concise Chinese output.",
                source_type=MemorySourceType.USER_PREFERENCE,
                authority=MemoryAuthorityLevel.USER_PROVIDED,
                allowed=(MemoryUsePurpose.RESPONSE_STYLE,),
            ).metadata_json,
        )
    )

    service = MemoryRetrievalService(SQLiteV1MemoryRetrievalAdapter(db_path=db_path))
    result = service.retrieve(
        MemoryRetrievalRequest(
            query="reply in Chinese",
            task_type=MemoryRetrievalTaskType.GENERAL_CHAT,
            user_id="u1",
            project_id="p1",
            country="mx",
            include_legacy_memory=False,
        )
    )

    assert [item.memory_id for item in result.items] == ["m4-1"]
