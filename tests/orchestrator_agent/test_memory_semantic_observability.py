from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.memory.contracts import (
    MemoryAuthorityLevel,
    MemorySourceType,
    MemoryUseDecision,
    MemoryUsePurpose,
)
from app.services.memory.retrieval import (
    MemoryRejectedRetrievalItem,
    MemoryRetrievalRequest,
    MemoryRetrievalResult,
    MemoryRetrievedItem,
)
from app.services.memory.retrieval_policy import MemoryRetrievalTaskType
from app.services.orchestrator_agent.memory_store import MemoryRecord, SQLiteMemoryStore
from app.services.orchestrator_agent.schemas import NormalizedRequest, OrchestratorSession, PlanStep


def _session() -> OrchestratorSession:
    now = datetime.now(timezone.utc)
    return OrchestratorSession(
        session_id="m6c-observability-session",
        created_at=now,
        updated_at=now,
        user_id="u1",
        project_id="p1",
        country="mx",
    )


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
) -> MemoryRecord:
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
    return MemoryRecord(
        memory_id=memory_id,
        scope="user",
        user_id=user_id,
        project_id=project_id,
        session_id=None,
        country=country,
        category="preference",
        memory_type="semantic",
        content=content,
        status=status,
        source="m4_write_gate",
        dedupe_key=f"dedupe-{memory_id}",
        metadata=metadata_json,
    )


class _FakeVectorIndex:
    def __init__(self, hits=None, error: Exception | None = None) -> None:
        self._hits = list(hits or [])
        self._error = error

    def search(self, *, query: str, top_k: int):
        if self._error is not None:
            raise self._error
        return list(self._hits[:top_k])

    def health_check(self):
        return {"ok": self._error is None}


def _item(memory_id: str, *, retrieval_method: str, content: str, score: float = 0.8) -> MemoryRetrievedItem:
    requested_use = MemoryUsePurpose.CONVERSATION_CONTEXT
    return MemoryRetrievedItem(
        memory_id=memory_id,
        content=content,
        memory_source_type=MemorySourceType.CONVERSATION,
        authority_level=MemoryAuthorityLevel.SYSTEM_GENERATED,
        allowed_memory_use=(requested_use,),
        forbidden_memory_use=(MemoryUsePurpose.PERMISSION_OVERRIDE,),
        requested_use=requested_use,
        use_decision=MemoryUseDecision(
            allowed=True,
            requested_use=requested_use,
            memory_source_type=MemorySourceType.CONVERSATION,
            authority_level=MemoryAuthorityLevel.SYSTEM_GENERATED,
            reason="memory use allowed",
            blocked_by=None,
        ),
        evidence_status=None,
        source_run_id=f"run-{memory_id}",
        source_artifact_id=f"artifact-{memory_id}",
        score=score,
        retrieval_method=retrieval_method,
        raw_distance=0.2 if retrieval_method == "vector" else None,
        normalized_score=score,
        metadata={},
    )


@pytest.mark.timeout(3)
def test_semantic_retriever_trace_records_fallback_reason_and_required_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings
    from app.services.memory.observability import SEMANTIC_MEMORY_TRACE_METADATA_KEY
    from app.services.memory.semantic_retrieval import SemanticMemoryRetrievalService

    monkeypatch.setattr(settings, "memory_vector_fallback_to_fts", True, raising=False)
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    service = SemanticMemoryRetrievalService(
        relational_store=store,
        vector_index=_FakeVectorIndex(error=RuntimeError("provider boom")),
    )

    result = service.retrieve(
        MemoryRetrievalRequest(
            query="style preference",
            task_type=MemoryRetrievalTaskType.GENERAL_CHAT,
            user_id="u1",
            project_id="p1",
            country="mx",
            allow_vector=True,
            allow_fts=False,
            max_vector_items=3,
            run_id="run-1",
            request_id="req-1",
            trace_id="trace-1",
        )
    )

    trace = result.metadata[SEMANTIC_MEMORY_TRACE_METADATA_KEY]
    assert trace["trace_id"] == "trace-1"
    assert trace["run_id"] == "run-1"
    assert trace["request_id"] == "req-1"
    assert trace["vector_candidate_count"] == 0
    assert trace["relational_loaded_count"] == 0
    assert trace["policy_allowed_count"] == 0
    assert trace["policy_blocked_count"] == 0
    assert trace["fallback_used"] is True
    assert trace["fallback_reason"] == "vector_search_error"


@pytest.mark.timeout(3)
def test_semantic_retriever_trace_aggregates_policy_block_reasons(tmp_path: Path) -> None:
    from app.services.memory.observability import SEMANTIC_MEMORY_TRACE_METADATA_KEY
    from app.services.memory.semantic_retrieval import SemanticMemoryRetrievalService
    from app.services.memory.vector_index_adapter import MemoryVectorQueryHit

    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    store.add(
        _record(
            memory_id="pref-1",
            content="User prefers concise Chinese output.",
            source_type=MemorySourceType.USER_PREFERENCE,
            authority=MemoryAuthorityLevel.USER_PROVIDED,
            allowed=(MemoryUsePurpose.RESPONSE_STYLE,),
            forbidden=(MemoryUsePurpose.RESPONSE_STYLE,),
        )
    )
    service = SemanticMemoryRetrievalService(
        relational_store=store,
        vector_index=_FakeVectorIndex(
            [
                MemoryVectorQueryHit(
                    memory_id="pref-1",
                    raw_distance=0.25,
                    normalized_score=0.8,
                )
            ]
        ),
    )

    result = service.retrieve(
        MemoryRetrievalRequest(
            query="What output style does the user prefer?",
            task_type=MemoryRetrievalTaskType.GENERAL_CHAT,
            user_id="u1",
            project_id="p1",
            country="mx",
            allow_vector=True,
            allow_fts=False,
            max_vector_items=3,
        )
    )

    trace = result.metadata[SEMANTIC_MEMORY_TRACE_METADATA_KEY]
    assert result.items == ()
    assert trace["vector_candidate_count"] == 1
    assert trace["relational_loaded_count"] == 1
    assert trace["policy_allowed_count"] == 0
    assert trace["policy_blocked_count"] == 1
    assert trace["policy_block_reasons"]["forbidden_use"] == 1


@pytest.mark.timeout(3)
def test_build_memory_context_bundle_adds_trace_summary_and_budget_metrics() -> None:
    from app.services.memory.context_builder import build_memory_context_bundle
    from app.services.memory.observability import (
        SEMANTIC_MEMORY_TRACE_METADATA_KEY,
        SEMANTIC_MEMORY_TRACE_SUMMARY_METADATA_KEY,
    )

    request = MemoryRetrievalRequest(
        query="conversation memory",
        task_type=MemoryRetrievalTaskType.GENERAL_CHAT,
        user_id="u1",
        project_id="p1",
        country="mx",
        allow_vector=True,
        allow_fts=True,
        retrieval_mode="fts_primary",
        max_items=2,
        max_vector_items=1,
    )
    result = MemoryRetrievalResult(
        request=request,
        items=(
            _item("fts-1", retrieval_method="fts", content="A" * 120),
            _item("vec-1", retrieval_method="vector", content="B" * 120),
        ),
        rejected_items=(
            MemoryRejectedRetrievalItem(
                memory_id="rej-1",
                requested_use=MemoryUsePurpose.CONVERSATION_CONTEXT,
                reason="requested use is explicitly forbidden",
                blocked_by="explicit_forbidden_use",
            ),
        ),
        warnings=(),
        metadata={},
    )

    bundle = build_memory_context_bundle(result, max_chars=320)
    trace = bundle.metadata[SEMANTIC_MEMORY_TRACE_METADATA_KEY]
    summary = bundle.metadata[SEMANTIC_MEMORY_TRACE_SUMMARY_METADATA_KEY]

    assert trace["injected_count"] == 1
    assert trace["context_budget_limit"] == 2
    assert trace["dropped_due_to_budget"] == 1
    assert summary["injected"] == 1
    assert summary["context_budget_limit"] == 2
    assert summary["warnings_count"] >= 1


@pytest.mark.timeout(3)
def test_build_retrieved_memory_context_writes_internal_semantic_handoff(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.memory.context_builder import MemoryContextBundle, MemoryContextItem
    from app.services.memory.observability import (
        SEMANTIC_MEMORY_TRACE_HANDOFF_KEY,
        SEMANTIC_MEMORY_TRACE_SUMMARY_METADATA_KEY,
    )
    from app.services.orchestrator_agent.memory_context import build_retrieved_memory_context
    from app.core.config import settings

    monkeypatch.setattr(settings, "memory_vector_context_injection_enabled", True, raising=False)

    summary = {
        "enabled": True,
        "retrieval_mode": "fts_primary",
        "requested_use": "response_style",
        "fts_candidates": 1,
        "vector_candidates": 1,
        "relational_loaded": 1,
        "policy_allowed": 1,
        "policy_blocked": 0,
        "injected": 1,
        "fallback_used": False,
        "fallback_reason": None,
        "context_budget_used": 1,
        "context_budget_limit": 8,
        "latency_ms": 1.2,
        "warnings_count": 0,
    }

    class _FakeHybridService:
        def build_context_bundle(self, **_: object):
            return MemoryContextBundle(
                task_type="general_chat",
                items=(
                    MemoryContextItem(
                        memory_id="pref-1",
                        header="[1] source_type=user_preference | authority=user_provided | use=response_style | retrieval=vector | evidence=none | memory_id=pref-1",
                        content="User prefers concise Chinese output.",
                        source_type="user_preference",
                        authority_level="user_provided",
                        evidence_status=None,
                        requested_use="response_style",
                        retrieval_method="vector",
                        source_run_id="run-pref-1",
                    ),
                ),
                warnings=(),
                rendered_text="Retrieved Memories:\n\n[1] source_type=user_preference | authority=user_provided | use=response_style | retrieval=vector | evidence=none | memory_id=pref-1\nUser prefers concise Chinese output.",
                metadata={
                    SEMANTIC_MEMORY_TRACE_SUMMARY_METADATA_KEY: summary,
                },
            )

    monkeypatch.setattr(
        "app.services.orchestrator_agent.memory_context.build_hybrid_memory_retrieval_service",
        lambda store=None: _FakeHybridService(),
    )

    session = _session()
    context, results = build_retrieved_memory_context(
        session=session,
        query="What style should I use?",
        country="mx",
    )

    assert "retrieval=vector" in context
    assert results[0]["memory_id"] == "pref-1"
    assert session.active_entities[SEMANTIC_MEMORY_TRACE_HANDOFF_KEY] == summary


def test_create_execution_trace_consumes_semantic_handoff_and_clears_it() -> None:
    from app.services.memory.observability import (
        EXECUTION_TRACE_SEMANTIC_MEMORY_KEY,
        SEMANTIC_MEMORY_TRACE_HANDOFF_KEY,
    )
    from app.services.orchestrator_agent.runtime.trace_store import create_execution_trace
    from app.services.orchestrator_agent.session_store import create_session

    session = create_session(country="mx")
    session.active_entities[SEMANTIC_MEMORY_TRACE_HANDOFF_KEY] = {
        "enabled": True,
        "retrieval_mode": "fts_primary",
        "requested_use": "response_style",
        "fts_candidates": 1,
        "vector_candidates": 1,
        "relational_loaded": 1,
        "policy_allowed": 1,
        "policy_blocked": 0,
        "injected": 1,
        "fallback_used": False,
        "fallback_reason": None,
        "context_budget_used": 1,
        "context_budget_limit": 8,
        "latency_ms": 1.2,
        "warnings_count": 0,
    }

    trace = create_execution_trace(
        session,
        execution_id="trace-1",
        turn_id="t1",
        run_id="r1",
        prompt="hello",
        normalized_request=NormalizedRequest(
            intent="general_chat",
            request_summary="hello",
        ),
        availability=None,
        steps=[PlanStep(step_id="s1", title="step", kind="demo")],
    )

    assert trace.internal_metadata[EXECUTION_TRACE_SEMANTIC_MEMORY_KEY]["enabled"] is True
    assert SEMANTIC_MEMORY_TRACE_HANDOFF_KEY not in session.active_entities


@pytest.mark.timeout(3)
def test_public_session_payload_hides_internal_active_entities(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.memory.observability import SEMANTIC_MEMORY_TRACE_HANDOFF_KEY
    from app.services.orchestrator_agent.session_store import create_session, save_session

    monkeypatch.setenv("MODEL_MODE", "mock")
    session = create_session(country="mx")
    session.active_entities["workspace_snapshot"] = {"country": "mx"}
    session.active_entities[SEMANTIC_MEMORY_TRACE_HANDOFF_KEY] = {"enabled": True}
    save_session(session)

    client = TestClient(app)
    payload = client.get(f"/api/orchestrator/sessions/{session.session_id}").json()

    assert payload["active_entities"]["workspace_snapshot"] == {"country": "mx"}
    assert SEMANTIC_MEMORY_TRACE_HANDOFF_KEY not in payload["active_entities"]
