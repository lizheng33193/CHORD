"""Real FAISS build/save/load foundation for M2D-8."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, UTC
from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session

from app.core.config import settings
from app.risk_knowledge.embedding.schemas import EmbeddingVectorResult
from app.risk_knowledge.indexing.errors import FaissManifestMismatchError, FaissUnavailableError
from app.risk_knowledge.indexing.schemas import (
    FaissBuildResult,
    FaissIndexManifest,
    FaissIndexManifestDraft,
    FaissVectorMappingEntry,
    LoadedFaissIndex,
    SavedFaissIndex,
)
from app.risk_knowledge.persistence.repositories import SqlAlchemyFaissIndexRepository


def build_faiss_fingerprint(
    *,
    kb_id: str,
    version_id: str,
    provider: str,
    model: str,
    dimension: int,
    chunk_content_pairs: list[tuple[str, str]],
) -> str:
    payload = json.dumps(
        {
            "kb_id": kb_id,
            "version_id": version_id,
            "provider": provider,
            "model": model,
            "dimension": dimension,
            "pairs": [[chunk_id, content_hash] for chunk_id, content_hash in sorted(chunk_content_pairs)],
            "record_count": len(chunk_content_pairs),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


class FaissIndexStore:
    def __init__(self, *, artifact_root: Path | None = None, db: Session | None = None) -> None:
        self._artifact_root = artifact_root or settings.resolve_path(settings.risk_knowledge_faiss_artifact_dir)
        self._db = db

    def build_index(
        self,
        embeddings: list[EmbeddingVectorResult],
        manifest_draft: FaissIndexManifestDraft,
    ) -> FaissBuildResult:
        if not embeddings:
            raise FaissManifestMismatchError("embeddings must not be empty")
        if manifest_draft.embedding_dimension <= 0:
            raise FaissManifestMismatchError("embedding dimension must be positive")

        sorted_embeddings = sorted(embeddings, key=lambda item: item.chunk_id)
        actual_pairs = [(item.chunk_id, item.content_hash) for item in sorted_embeddings]
        expected_pairs = sorted(manifest_draft.chunk_content_pairs)
        if actual_pairs != expected_pairs:
            raise FaissManifestMismatchError("manifest chunk/content pairs do not match embedding set")
        if any(len(item.vector) != manifest_draft.embedding_dimension for item in sorted_embeddings):
            raise FaissManifestMismatchError("embedding dimension mismatch for FAISS build")
        faiss = self._require_faiss()

        vectors = np.array([item.vector for item in sorted_embeddings], dtype="float32")
        ids = np.array(list(range(len(sorted_embeddings))), dtype="int64")

        if manifest_draft.index_type != "flat_l2" or manifest_draft.distance_metric != "l2":
            raise FaissManifestMismatchError("only flat_l2 / l2 is supported in M2D-8")

        index = faiss.IndexIDMap2(faiss.IndexFlatL2(manifest_draft.embedding_dimension))
        index.add_with_ids(vectors, ids)

        mapping = {
            int(vector_id): FaissVectorMappingEntry(
                chunk_id=item.chunk_id,
                embedding_id=self._build_embedding_id(item),
                content_hash=item.content_hash,
            )
            for vector_id, item in zip(ids.tolist(), sorted_embeddings)
        }

        manifest = FaissIndexManifest(
            index_id=manifest_draft.index_id,
            kb_id=manifest_draft.kb_id,
            version_id=manifest_draft.version_id,
            embedding_provider=manifest_draft.embedding_provider,
            embedding_model=manifest_draft.embedding_model,
            embedding_dimension=manifest_draft.embedding_dimension,
            job_id=manifest_draft.job_id,
            index_type=manifest_draft.index_type,
            distance_metric=manifest_draft.distance_metric,
            record_count=len(sorted_embeddings),
            artifact_path=str(self._artifact_root / f"{manifest_draft.index_id}.faiss"),
            mapping_path=str(self._artifact_root / f"{manifest_draft.index_id}.mapping.json"),
            checksum="pending",
            build_fingerprint=build_faiss_fingerprint(
                kb_id=manifest_draft.kb_id,
                version_id=manifest_draft.version_id,
                provider=manifest_draft.embedding_provider,
                model=manifest_draft.embedding_model,
                dimension=manifest_draft.embedding_dimension,
                chunk_content_pairs=actual_pairs,
            ),
            build_status="built",
            is_active=False,
            superseded_by_index_id=None,
            superseded_at=None,
            built_at=datetime.now(UTC),
        )
        return FaissBuildResult(index=index, manifest=manifest, vector_mappings=mapping)

    def save_index(self, build_result: FaissBuildResult) -> SavedFaissIndex:
        faiss = self._require_faiss()
        artifact_path = Path(build_result.manifest.artifact_path)
        mapping_path = Path(build_result.manifest.mapping_path)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        mapping_path.parent.mkdir(parents=True, exist_ok=True)

        artifact_tmp_path = artifact_path.with_name(f"{artifact_path.name}.tmp")
        mapping_tmp_path = mapping_path.with_name(f"{mapping_path.name}.tmp")

        faiss.write_index(build_result.index, str(artifact_tmp_path))
        mapping_payload = {
            str(vector_id): entry.model_dump()
            for vector_id, entry in build_result.vector_mappings.items()
        }
        mapping_tmp_path.write_text(json.dumps(mapping_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        checksum = self._compute_artifact_checksum(artifact_tmp_path, mapping_tmp_path)
        os.replace(artifact_tmp_path, artifact_path)
        os.replace(mapping_tmp_path, mapping_path)
        manifest = build_result.manifest.model_copy(update={"checksum": checksum, "build_status": "saved"})

        if self._db is not None:
            repo = SqlAlchemyFaissIndexRepository(self._db)
            repo.save_manifest(manifest)
            repo.replace_vector_mappings(index_id=manifest.index_id, mappings=build_result.vector_mappings)
            self._db.commit()

        return SavedFaissIndex(manifest=manifest, vector_mappings=build_result.vector_mappings)

    def load_index(self, manifest: FaissIndexManifest) -> LoadedFaissIndex:
        faiss = self._require_faiss()
        artifact_path = Path(manifest.artifact_path)
        mapping_path = Path(manifest.mapping_path)
        checksum = self._compute_artifact_checksum(artifact_path, mapping_path)
        if manifest.checksum != checksum:
            raise FaissManifestMismatchError("FAISS artifact checksum mismatch")
        index = faiss.read_index(str(artifact_path))
        mapping_payload = json.loads(mapping_path.read_text(encoding="utf-8"))
        mappings = {
            int(vector_id): FaissVectorMappingEntry.model_validate(entry)
            for vector_id, entry in mapping_payload.items()
        }
        return LoadedFaissIndex(index=index, manifest=manifest, vector_mappings=mappings)

    def _require_faiss(self):
        try:
            import faiss
        except Exception as exc:  # pylint: disable=broad-except
            raise FaissUnavailableError(
                "faiss is not installed; add faiss-cpu to requirements before using M2D-8 FAISS foundation"
            ) from exc
        return faiss

    def _compute_artifact_checksum(self, artifact_path: Path, mapping_path: Path) -> str:
        digest = hashlib.sha256()
        digest.update(artifact_path.read_bytes())
        digest.update(mapping_path.read_bytes())
        return f"sha256:{digest.hexdigest()}"

    def _build_embedding_id(self, result: EmbeddingVectorResult) -> str:
        checksum = hashlib.sha256(
            f"{result.chunk_id}|{result.provider}|{result.model}|{result.dimension}|{result.content_hash}".encode("utf-8")
        ).hexdigest()[:12]
        return f"emb_{result.chunk_id}_{checksum}"
