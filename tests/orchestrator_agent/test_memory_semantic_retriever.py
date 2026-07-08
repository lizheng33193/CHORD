from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import settings
from app.services.memory.contracts import (
    MemoryAuthorityLevel,
    MemorySourceType,
    MemoryUsePurpose,
)
from app.services.memory.retrieval import MemoryRetrievalRequest
from app.services.memory.retrieval_policy import MemoryRetrievalTaskType
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
):
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


def test_semantic_retriever_returns_policy_gated_vector_candidate(tmp_path: Path) -> None:
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

    assert [item.memory_id for item in result.items] == ["pref-1"]
    assert result.items[0].retrieval_method == "vector"
    assert result.items[0].raw_distance == pytest.approx(0.25)
    assert result.items[0].normalized_score == pytest.approx(0.8)
    assert result.rejected_items == ()


def test_semantic_retriever_blocks_invisible_candidate_and_falls_back_on_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.memory.semantic_retrieval import SemanticMemoryRetrievalService
    from app.services.memory.vector_index_adapter import MemoryVectorQueryHit

    monkeypatch.setattr(settings, "memory_vector_fallback_to_fts", True, raising=False)
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    store.add(
        _record(
            memory_id="pref-1",
            content="User prefers concise Chinese output.",
            source_type=MemorySourceType.USER_PREFERENCE,
            authority=MemoryAuthorityLevel.USER_PROVIDED,
            allowed=(MemoryUsePurpose.RESPONSE_STYLE,),
            user_id="other-user",
        )
    )
    invisible_service = SemanticMemoryRetrievalService(
        relational_store=store,
        vector_index=_FakeVectorIndex(
            [MemoryVectorQueryHit(memory_id="pref-1", raw_distance=0.4, normalized_score=0.7)]
        ),
    )

    invisible = invisible_service.retrieve(
        MemoryRetrievalRequest(
            query="style preference",
            task_type=MemoryRetrievalTaskType.GENERAL_CHAT,
            user_id="u1",
            project_id="p1",
            country="mx",
            allow_vector=True,
            allow_fts=False,
            max_vector_items=3,
        )
    )

    assert invisible.items == ()
    assert [item.blocked_by for item in invisible.rejected_items] == ["not_visible_or_missing"]

    failing_service = SemanticMemoryRetrievalService(
        relational_store=store,
        vector_index=_FakeVectorIndex(error=RuntimeError("provider boom")),
    )
    failed = failing_service.retrieve(
        MemoryRetrievalRequest(
            query="style preference",
            task_type=MemoryRetrievalTaskType.GENERAL_CHAT,
            user_id="u1",
            project_id="p1",
            country="mx",
            allow_vector=True,
            allow_fts=False,
            max_vector_items=3,
        )
    )

    assert failed.items == ()
    assert "vector_search_failed" in failed.warnings
    assert failed.metadata["used_fallback"] is True
