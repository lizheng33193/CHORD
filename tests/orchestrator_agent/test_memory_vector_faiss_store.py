from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.orchestrator_agent.memory_vector.schemas import (
    MemoryVectorManifest,
    MemoryVectorMetadata,
    MemoryVectorRecord,
)


def _record(
    memory_id: str,
    vector: list[float],
    *,
    embedding_text_hash: str | None = None,
    status: str = "indexed",
) -> MemoryVectorRecord:
    return MemoryVectorRecord(
        memory_id=memory_id,
        embedding_text=f"text for {memory_id}",
        embedding_text_hash=embedding_text_hash or f"sha256:{memory_id}",
        content_hash=f"sha256:content:{memory_id}",
        embedding=vector,
        metadata=MemoryVectorMetadata(
            memory_id=memory_id,
            user_id="u1",
            project_id="p1",
            country="mx",
            category="reference",
            memory_type="semantic",
            source="memory_admin",
            status="active",
            importance=0.8,
            confidence=0.9,
            created_at="2026-07-08T00:00:00+00:00",
            updated_at="2026-07-08T00:00:00+00:00",
            content_hash=f"sha256:content:{memory_id}",
            embedding_provider="deterministic",
            embedding_model="memory-fake-embedding-v1",
            embedding_dim=len(vector),
            vector_status=status,
            is_current=True,
            metadata={},
        ),
    )


def _manifest(namespace: str = "default", *, dimension: int = 2) -> MemoryVectorManifest:
    return MemoryVectorManifest(
        namespace=namespace,
        embedding_provider="deterministic",
        embedding_model="memory-fake-embedding-v1",
        embedding_dim=dimension,
        index_type="flat_l2",
        distance_metric="l2",
        record_count=0,
        checksum="",
        built_at="2026-07-08T00:00:00+00:00",
    )


def test_memory_faiss_store_upsert_search_and_reload_round_trip(tmp_path: Path) -> None:
    faiss = pytest.importorskip("faiss")
    assert faiss is not None

    from app.services.orchestrator_agent.memory_vector.faiss_store import MemoryFaissStore

    store = MemoryFaissStore(index_dir=tmp_path, manifest=_manifest())
    store.upsert(
        [
            _record("mem-1", [1.0, 0.0]),
            _record("mem-2", [0.0, 1.0]),
        ]
    )
    store.persist()

    loaded = MemoryFaissStore(index_dir=tmp_path, manifest=_manifest())
    results = loaded.search([1.0, 0.0], top_k=1)

    assert results
    assert results[0].memory_id == "mem-1"
    assert results[0].raw_distance == 0.0
    assert results[0].score == 1.0


def test_memory_faiss_store_filters_deleted_and_dedupes_current_vectors(tmp_path: Path) -> None:
    pytest.importorskip("faiss")
    from app.services.orchestrator_agent.memory_vector.faiss_store import MemoryFaissStore

    store = MemoryFaissStore(index_dir=tmp_path, manifest=_manifest())
    store.upsert([_record("mem-1", [1.0, 0.0], embedding_text_hash="sha256:v1")])
    store.upsert([_record("mem-1", [1.0, 0.0], embedding_text_hash="sha256:v2")])
    store.upsert([_record("mem-2", [0.0, 1.0])])

    results = store.search([1.0, 0.0], top_k=2)
    assert [item.memory_id for item in results] == ["mem-1", "mem-2"]
    assert len([item for item in results if item.memory_id == "mem-1"]) == 1

    store.delete(["mem-1"])
    after_delete = store.search([1.0, 0.0], top_k=2)
    assert all(item.memory_id != "mem-1" for item in after_delete)


def test_memory_faiss_store_rebuild_cleans_inactive_vectors(tmp_path: Path) -> None:
    pytest.importorskip("faiss")
    from app.services.orchestrator_agent.memory_vector.faiss_store import MemoryFaissStore

    store = MemoryFaissStore(index_dir=tmp_path, manifest=_manifest())
    first = _record("mem-1", [1.0, 0.0], embedding_text_hash="sha256:v1")
    second = _record("mem-1", [1.0, 0.0], embedding_text_hash="sha256:v2")
    third = _record("mem-2", [0.0, 1.0])
    store.upsert([first, second, third])
    store.delete(["mem-2"])
    store.persist()

    store.rebuild([second])
    store.persist()

    metadata_path = tmp_path / "metadata.json"
    assert metadata_path.exists()
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    memory_ids = [entry["memory_id"] for entry in payload.values()]
    assert "mem-2" not in memory_ids
    assert memory_ids == ["mem-1"]
