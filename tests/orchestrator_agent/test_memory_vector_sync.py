from __future__ import annotations

from pathlib import Path

from app.services.orchestrator_agent.memory_policy import build_memory_record
from app.services.orchestrator_agent.memory_store import SQLiteMemoryStore
from app.services.orchestrator_agent.memory_vector.faiss_store import MemoryFaissStore
from app.services.orchestrator_agent.memory_vector.provider import (
    DeterministicMemoryEmbeddingProvider,
)
from app.services.orchestrator_agent.memory_vector.schemas import MemoryVectorManifest
from app.services.orchestrator_agent.memory_vector.sync import MemoryVectorSyncService


def _manifest(*, dimension: int = 4) -> MemoryVectorManifest:
    return MemoryVectorManifest(
        namespace="default",
        embedding_provider="deterministic",
        embedding_model="memory-fake-embedding-v1",
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
    user_id: str = "u1",
    project_id: str = "p1",
    country: str = "mx",
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


def test_memory_vector_sync_indexes_active_memory_and_records_status(tmp_path: Path) -> None:
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    record = _add_memory(store, "请记住：我偏好中文输出，并且回答要简洁")
    service = MemoryVectorSyncService(
        relational_store=store,
        vector_store=MemoryFaissStore(index_dir=tmp_path / "vector", manifest=_manifest()),
        embedding_provider=DeterministicMemoryEmbeddingProvider(dimension=4),
    )

    result = service.sync_memory(record.memory_id)
    sync_state = service.get_sync_status(record.memory_id)

    assert result.status == "indexed"
    assert sync_state is not None
    assert sync_state.vector_status == "indexed"
    assert sync_state.embedding_text_hash is not None
    assert sync_state.indexed_at is not None


def test_memory_vector_sync_records_failed_status_when_embedding_provider_breaks(tmp_path: Path) -> None:
    class FailingProvider:
        provider_name = "deterministic"
        model_name = "memory-fake-embedding-v1"
        dimension = 4

        def embed_texts(self, texts: list[str], *, input_type: str = "document") -> list[list[float]]:
            raise RuntimeError("embedding backend unavailable")

    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    record = _add_memory(store, "项目事实：当前项目使用 SQLite 长期记忆", category="project")
    service = MemoryVectorSyncService(
        relational_store=store,
        vector_store=MemoryFaissStore(index_dir=tmp_path / "vector", manifest=_manifest()),
        embedding_provider=FailingProvider(),
    )

    result = service.sync_memory(record.memory_id)
    sync_state = service.get_sync_status(record.memory_id)

    assert result.status == "failed"
    assert "embedding backend unavailable" in (result.error or "")
    assert sync_state is not None
    assert sync_state.vector_status == "failed"
    assert "embedding backend unavailable" in (sync_state.last_error or "")


def test_memory_vector_sync_marks_deleted_and_restore_requeues_indexing(tmp_path: Path) -> None:
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    record = _add_memory(store, "请记住：我默认使用 Markdown 表格")
    service = MemoryVectorSyncService(
        relational_store=store,
        vector_store=MemoryFaissStore(index_dir=tmp_path / "vector", manifest=_manifest()),
        embedding_provider=DeterministicMemoryEmbeddingProvider(dimension=4),
    )

    service.sync_memory(record.memory_id)
    archived = store.set_status(record.memory_id, status="archived", user_id="u1", project_id="p1", country="mx")
    deleted_state = store.get_vector_sync_state(archived["memory_id"])
    restored = store.set_status(record.memory_id, status="active", user_id="u1", project_id="p1", country="mx")
    restored_state = store.get_vector_sync_state(restored["memory_id"])

    assert deleted_state is not None
    assert deleted_state.vector_status == "deleted"
    assert restored_state is not None
    assert restored_state.vector_status in {"pending", "stale", "indexed"}
