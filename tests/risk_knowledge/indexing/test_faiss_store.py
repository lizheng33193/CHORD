from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.risk_knowledge.embedding.schemas import EmbeddingVectorResult


def _build_embeddings() -> list[EmbeddingVectorResult]:
    return [
        EmbeddingVectorResult(
            chunk_id="risk_guide_202607_chunk_000001",
            content_hash="sha256:one",
            provider="deterministic_test",
            model="deterministic-v1",
            dimension=2,
            vector=[1.0, 0.0],
            vector_checksum="sha256:v1",
        ),
        EmbeddingVectorResult(
            chunk_id="risk_guide_202607_chunk_000002",
            content_hash="sha256:two",
            provider="deterministic_test",
            model="deterministic-v1",
            dimension=2,
            vector=[0.0, 1.0],
            vector_checksum="sha256:v2",
        ),
    ]


def test_build_fingerprint_changes_when_content_hashes_change() -> None:
    from app.risk_knowledge.indexing.faiss_store import build_faiss_fingerprint

    first = build_faiss_fingerprint(
        kb_id="risk_domain_knowledge",
        version_id="risk_guide_202607",
        provider="deterministic_test",
        model="deterministic-v1",
        dimension=2,
        chunk_content_pairs=[("a", "sha256:1"), ("b", "sha256:2")],
    )
    second = build_faiss_fingerprint(
        kb_id="risk_domain_knowledge",
        version_id="risk_guide_202607",
        provider="deterministic_test",
        model="deterministic-v1",
        dimension=2,
        chunk_content_pairs=[("a", "sha256:1"), ("b", "sha256:3")],
    )

    assert first != second


def test_faiss_store_build_rejects_manifest_mismatch(tmp_path: Path) -> None:
    from app.risk_knowledge.indexing.errors import FaissManifestMismatchError
    from app.risk_knowledge.indexing.faiss_store import FaissIndexStore
    from app.risk_knowledge.indexing.schemas import FaissIndexManifestDraft

    store = FaissIndexStore(artifact_root=tmp_path)
    manifest = FaissIndexManifestDraft(
        index_id="idx_risk_guide_202607",
        kb_id="risk_domain_knowledge",
        version_id="risk_guide_202607",
        embedding_provider="deterministic_test",
        embedding_model="deterministic-v1",
        embedding_dimension=99,
        index_type="flat_l2",
        distance_metric="l2",
        chunk_content_pairs=[(item.chunk_id, item.content_hash) for item in _build_embeddings()],
    )

    with pytest.raises(FaissManifestMismatchError):
        store.build_index(_build_embeddings(), manifest)


def test_faiss_store_save_and_load_round_trip(tmp_path: Path) -> None:
    faiss = pytest.importorskip("faiss")
    from app.risk_knowledge.indexing.faiss_store import FaissIndexStore
    from app.risk_knowledge.indexing.schemas import FaissIndexManifestDraft

    store = FaissIndexStore(artifact_root=tmp_path)
    manifest = FaissIndexManifestDraft(
        index_id="idx_risk_guide_202607",
        kb_id="risk_domain_knowledge",
        version_id="risk_guide_202607",
        embedding_provider="deterministic_test",
        embedding_model="deterministic-v1",
        embedding_dimension=2,
        index_type="flat_l2",
        distance_metric="l2",
        chunk_content_pairs=[(item.chunk_id, item.content_hash) for item in _build_embeddings()],
    )

    built = store.build_index(_build_embeddings(), manifest)
    saved = store.save_index(built)
    loaded = store.load_index(saved.manifest)

    assert saved.manifest.record_count == 2
    assert loaded.manifest.index_id == "idx_risk_guide_202607"
    assert list(loaded.vector_mappings.keys()) == [0, 1]
    distances, ids = loaded.index.search(np.array([[1.0, 0.0]], dtype="float32"), 1)
    assert ids.shape == (1, 1)
    assert int(ids[0][0]) == 0
