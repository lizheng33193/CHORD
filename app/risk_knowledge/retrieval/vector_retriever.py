"""FAISS vector retrieval for M2D-10."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from app.risk_knowledge.indexing.errors import FaissManifestMismatchError
from app.risk_knowledge.indexing.faiss_store import FaissIndexStore
from app.risk_knowledge.indexing.schemas import FaissIndexManifest
from app.risk_knowledge.retrieval.errors import (
    ManifestArtifactMissingError,
    ManifestChecksumMismatchError,
    QueryEmbeddingDimensionMismatchError,
    UnsupportedVectorDistanceMetricError,
    VectorMappingMissingError,
    VectorSearchError,
)
from app.risk_knowledge.retrieval.schemas import ActiveRetrievalScope, VectorRetrievalHit


class FaissVectorRetriever:
    def __init__(self, *, store: FaissIndexStore | None = None) -> None:
        self._store = store or FaissIndexStore()

    def search(self, query_vector: list[float], scope: ActiveRetrievalScope, top_k: int) -> list[VectorRetrievalHit]:
        hits: list[VectorRetrievalHit] = []
        for manifest in scope.manifests:
            if manifest.distance_metric != "l2":
                raise UnsupportedVectorDistanceMetricError(
                    f"unsupported vector distance metric: {manifest.distance_metric}"
                )
            if len(query_vector) != manifest.embedding_dimension:
                raise QueryEmbeddingDimensionMismatchError(
                    f"expected query dimension {manifest.embedding_dimension}, got {len(query_vector)}"
                )
            if not Path(manifest.artifact_path).exists() or not Path(manifest.mapping_path).exists():
                raise ManifestArtifactMissingError(
                    f"manifest artifact is missing for index_id={manifest.manifest_index_id}"
                )
            loaded = self._load_manifest(manifest)
            if not loaded.vector_mappings:
                raise VectorMappingMissingError(
                    f"vector mapping missing for index_id={manifest.manifest_index_id}"
                )
            effective_top_k = min(top_k, len(loaded.vector_mappings))
            if effective_top_k <= 0:
                raise VectorMappingMissingError(
                    f"vector mapping missing for index_id={manifest.manifest_index_id}"
                )
            try:
                distances, ids = loaded.index.search(
                    np.array([query_vector], dtype="float32"),
                    effective_top_k,
                )
            except Exception as exc:  # pylint: disable=broad-except
                raise VectorSearchError(str(exc)) from exc

            for raw_score, vector_id in zip(distances[0].tolist(), ids[0].tolist(), strict=False):
                if int(vector_id) < 0:
                    continue
                mapping = loaded.vector_mappings.get(int(vector_id))
                if mapping is None:
                    raise VectorMappingMissingError(
                        f"vector id {vector_id} missing for index_id={manifest.manifest_index_id}"
                    )
                hits.append(
                    VectorRetrievalHit(
                        retrieval_key=_build_retrieval_key(manifest.manifest_index_id, mapping.chunk_id),
                        chunk_id=mapping.chunk_id,
                        document_id=manifest.document_id,
                        version_id=manifest.version_id,
                        manifest_index_id=manifest.manifest_index_id,
                        vector_id=int(vector_id),
                        raw_score=float(raw_score),
                        distance_metric=manifest.distance_metric,
                        rank=1,
                    )
                )

        ordered = sorted(hits, key=lambda item: (item.raw_score, item.retrieval_key))
        ranked = [
            item.model_copy(update={"rank": rank})
            for rank, item in enumerate(ordered[:top_k], start=1)
        ]
        return ranked

    def _load_manifest(self, manifest):
        try:
            return self._store.load_index(
                FaissIndexManifest(
                    index_id=manifest.manifest_index_id,
                    kb_id=manifest.kb_id,
                    version_id=manifest.version_id,
                    embedding_provider=manifest.embedding_provider,
                    embedding_model=manifest.embedding_model,
                    embedding_dimension=manifest.embedding_dimension,
                    job_id=None,
                    index_type="flat_l2",
                    distance_metric=manifest.distance_metric,
                    record_count=0,
                    artifact_path=manifest.artifact_path,
                    mapping_path=manifest.mapping_path,
                    checksum=manifest.checksum,
                    build_fingerprint=manifest.build_fingerprint,
                    build_status="active",
                    is_active=True,
                    superseded_by_index_id=None,
                    superseded_at=None,
                    built_at=datetime.now(UTC),
                )
            )
        except FileNotFoundError as exc:
            raise ManifestArtifactMissingError(str(exc)) from exc
        except FaissManifestMismatchError as exc:
            raise ManifestChecksumMismatchError(str(exc)) from exc
        except ManifestArtifactMissingError:
            raise
        except Exception as exc:  # pylint: disable=broad-except
            raise VectorSearchError(str(exc)) from exc


def _build_retrieval_key(manifest_index_id: str, chunk_id: str) -> str:
    return f"{manifest_index_id}:{chunk_id}"
