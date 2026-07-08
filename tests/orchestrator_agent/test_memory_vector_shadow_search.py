from __future__ import annotations

from pathlib import Path

from app.services.orchestrator_agent.memory_policy import build_memory_record
from app.services.orchestrator_agent.memory_store import SQLiteMemoryStore
from app.services.orchestrator_agent.memory_vector.faiss_store import (
    MemoryFaissStore,
    MemoryVectorCompatibilityError,
)
from app.services.orchestrator_agent.memory_vector.provider import (
    DeterministicMemoryEmbeddingProvider,
)
from app.services.orchestrator_agent.memory_vector.schemas import MemoryVectorManifest
from app.services.orchestrator_agent.memory_vector.shadow_search import (
    shadow_search_memory,
)
from app.services.orchestrator_agent.memory_vector.sync import MemoryVectorSyncService


def _manifest(*, model: str = "memory-fake-embedding-v1", dimension: int = 4) -> MemoryVectorManifest:
    return MemoryVectorManifest(
        namespace="default",
        embedding_provider="deterministic",
        embedding_model=model,
        embedding_dim=dimension,
        index_type="flat_l2",
        distance_metric="l2",
        record_count=0,
        checksum="",
        built_at="2026-07-08T00:00:00+00:00",
    )


def _add_memory(
    store: SQLiteMemoryStore,
    content: str,
    *,
    user_id: str,
    project_id: str,
    country: str,
    category: str = "preference",
):
    decision = build_memory_record(
        content=content,
        category=category,
        user_id=user_id,
        project_id=project_id,
        country=country,
        session_id="s1",
    )
    assert decision.accepted and decision.record
    return store.add(decision.record)


def test_shadow_search_returns_scoped_candidates_after_relational_load(tmp_path: Path) -> None:
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    primary = _add_memory(store, "请记住：我偏好中文输出", user_id="u1", project_id="p1", country="mx")
    _add_memory(store, "请记住：我偏好英文输出", user_id="u2", project_id="p1", country="mx")
    _add_memory(store, "请记住：我偏好西语输出", user_id="u1", project_id="p1", country="th")
    provider = DeterministicMemoryEmbeddingProvider(dimension=4)
    vector_store = MemoryFaissStore(index_dir=tmp_path / "vector", manifest=_manifest())
    service = MemoryVectorSyncService(
        relational_store=store,
        vector_store=vector_store,
        embedding_provider=provider,
    )
    service.sync_all_active()

    result = shadow_search_memory(
        "我之前的输出偏好是什么？",
        user_id="u1",
        project_id="p1",
        country="mx",
        top_k=3,
        relational_store=store,
        vector_store=vector_store,
        embedding_provider=provider,
    )

    assert result.candidates
    assert result.candidates[0].memory_id == primary.memory_id
    assert "中文输出" in result.candidates[0].memory["content"]
    assert all(item.memory["user_id"] == "u1" for item in result.candidates)
    assert all(item.memory["country"] == "mx" for item in result.candidates)


def test_shadow_search_filters_archived_memory_without_changing_fts_results(tmp_path: Path) -> None:
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    record = _add_memory(store, "项目事实：当前项目使用 SQLite 长期记忆", user_id="u1", project_id="p1", country="mx", category="project")
    provider = DeterministicMemoryEmbeddingProvider(dimension=4)
    vector_store = MemoryFaissStore(index_dir=tmp_path / "vector", manifest=_manifest())
    service = MemoryVectorSyncService(
        relational_store=store,
        vector_store=vector_store,
        embedding_provider=provider,
    )
    service.sync_memory(record.memory_id)
    before_archive = store.search("SQLite 长期记忆", user_id="u1", project_id="p1", country="mx")
    store.set_status(record.memory_id, status="archived", user_id="u1", project_id="p1", country="mx")
    after_archive = store.search("SQLite 长期记忆", user_id="u1", project_id="p1", country="mx")

    result = shadow_search_memory(
        "SQLite 长期记忆",
        user_id="u1",
        project_id="p1",
        country="mx",
        top_k=3,
        relational_store=store,
        vector_store=vector_store,
        embedding_provider=provider,
    )

    assert before_archive
    assert after_archive == []
    assert result.candidates == ()
    assert result.filtered_out
    assert result.filtered_out[0].memory_id == record.memory_id


def test_shadow_search_fails_closed_on_manifest_mismatch(tmp_path: Path) -> None:
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    record = _add_memory(store, "请记住：我偏好表格输出", user_id="u1", project_id="p1", country="mx")
    provider = DeterministicMemoryEmbeddingProvider(dimension=4)
    vector_dir = tmp_path / "vector"
    service = MemoryVectorSyncService(
        relational_store=store,
        vector_store=MemoryFaissStore(index_dir=vector_dir, manifest=_manifest()),
        embedding_provider=provider,
    )
    service.sync_memory(record.memory_id)

    try:
        MemoryFaissStore(index_dir=vector_dir, manifest=_manifest(model="other-model"))
    except MemoryVectorCompatibilityError:
        return

    raise AssertionError("memory vector store must fail closed on manifest mismatch")
