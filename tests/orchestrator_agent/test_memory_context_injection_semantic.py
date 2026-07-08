from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.core.config import settings
from app.services.orchestrator_agent.memory_context import build_retrieved_memory_context
from app.services.orchestrator_agent.memory_policy import build_memory_record
from app.services.orchestrator_agent.memory_store import SQLiteMemoryStore
from app.services.orchestrator_agent.schemas import OrchestratorSession


def _session() -> OrchestratorSession:
    now = datetime.now(timezone.utc)
    return OrchestratorSession(
        session_id="m6b-memory-context",
        created_at=now,
        updated_at=now,
        user_id="u1",
        project_id="p1",
        country="mx",
    )


def _legacy_context(store: SQLiteMemoryStore, *, query: str, user_id: str, project_id: str, country: str):
    results = store.search(query=query, user_id=user_id, project_id=project_id, country=country, top_k=8)
    if not results:
        return "", []
    lines = [
        "## Retrieved Memories",
        "Use these persisted memories as user/project facts when they are relevant. "
        "If the user asks about their preferences, answer from preference memories "
        "before generic system output-style rules.",
    ]
    for item in results:
        lines.append(f"- [{item.get('category', 'memory')} score={item.get('score', 0)}] {item.get('content', '')}")
    return "\n".join(lines), results


@pytest.mark.timeout(3)
def test_build_retrieved_memory_context_flag_off_matches_legacy_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "memory_vector_context_injection_enabled", False, raising=False)
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    decision = build_memory_record(
        content="请记住：我偏好中文输出",
        category="preference",
        user_id="u1",
        project_id="p1",
        country="mx",
    )
    assert decision.accepted and decision.record
    store.add(decision.record)

    expected_context, expected_results = _legacy_context(
        store,
        query="中文输出",
        user_id="u1",
        project_id="p1",
        country="mx",
    )
    actual_context, actual_results = build_retrieved_memory_context(
        session=_session(),
        query="中文输出",
        country="mx",
        store=store,
    )

    assert actual_context == expected_context
    assert actual_results == expected_results


@pytest.mark.timeout(3)
def test_build_retrieved_memory_context_flag_on_uses_hybrid_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.memory.context_builder import MemoryContextBundle, MemoryContextItem

    monkeypatch.setattr(settings, "memory_vector_context_injection_enabled", True, raising=False)

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
                metadata={},
            )

    monkeypatch.setattr(
        "app.services.orchestrator_agent.memory_context.build_hybrid_memory_retrieval_service",
        lambda store=None: _FakeHybridService(),
    )

    context, results = build_retrieved_memory_context(
        session=_session(),
        query="What style should I use?",
        country="mx",
    )

    assert "retrieval=vector" in context
    assert results[0]["memory_id"] == "pref-1"
    assert results[0]["retrieval_method"] == "vector"


@pytest.mark.timeout(3)
def test_build_retrieved_memory_context_sql_path_does_not_use_vector_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "memory_vector_context_injection_enabled", True, raising=False)
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    decision = build_memory_record(
        content="项目事实：当前项目使用 SQLite 长期记忆",
        category="project",
        user_id="u1",
        project_id="p1",
        country="mx",
    )
    assert decision.accepted and decision.record
    store.add(decision.record)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("hybrid runtime should not run for SQL/Data Agent paths")

    monkeypatch.setattr(
        "app.services.orchestrator_agent.memory_context.build_hybrid_memory_retrieval_service",
        _fail_if_called,
    )

    context, results = build_retrieved_memory_context(
        session=_session(),
        query="请给我一个 SQL repair hint",
        country="mx",
        store=store,
    )

    assert "Retrieved Memories" in context
    assert results
