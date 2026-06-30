from __future__ import annotations

from pathlib import Path

import pytest

from app.knowledge_base.schemas import (
    ChunkStatus,
    DocumentStatus,
    DocumentVersionStatus,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    PermissionScope,
    SourceType,
)
from app.risk_knowledge.embedding.schemas import EmbeddingInput, EmbeddingVectorResult


@pytest.fixture()
def auth_db(tmp_path: Path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "auth_database_url", f"sqlite:///{tmp_path / 'auth.sqlite3'}", raising=False)
    monkeypatch.setattr(settings, "auth_jwt_secret", "test-secret-for-m2d10", raising=False)
    monkeypatch.setattr(settings, "default_admin_username", "admin", raising=False)
    monkeypatch.setattr(settings, "default_admin_email", "admin@example.com", raising=False)
    monkeypatch.setattr(settings, "default_admin_password", "admin123456", raising=False)

    from app.auth.database import AuthSessionLocal, create_auth_schema, reset_auth_engine
    from app.auth.seed import seed_auth_data

    reset_auth_engine()
    create_auth_schema()
    with AuthSessionLocal() as db:
        seed_auth_data(db)

    yield tmp_path

    reset_auth_engine()


class DeterministicRetrievalEmbeddingProvider:
    provider_name = "deterministic_test"

    def __init__(self, *, dimension: int = 2) -> None:
        self._dimension = dimension

    def embed(self, inputs: list[EmbeddingInput]) -> list[EmbeddingVectorResult]:
        results: list[EmbeddingVectorResult] = []
        for item in inputs:
            if self._dimension == 2:
                vector = [float(len(item.text)), float(len(item.chunk_id))]
            else:
                vector = [float(index + 1) for index in range(self._dimension)]
            results.append(
                EmbeddingVectorResult(
                    chunk_id=item.chunk_id,
                    content_hash=item.content_hash,
                    provider=self.provider_name,
                    model="deterministic-v1",
                    dimension=self._dimension,
                    vector=vector,
                    vector_checksum=f"sha256:{item.chunk_id}:{self._dimension}",
                )
            )
        return results


def _build_document(*, doc_id: str, current_version_id: str | None = None, status: DocumentStatus = DocumentStatus.ACTIVE) -> KnowledgeDocument:
    return KnowledgeDocument(
        doc_id=doc_id,
        kb_id="risk_domain_knowledge",
        doc_title=f"{doc_id} title",
        doc_name=f"{doc_id}.pdf",
        source_type=SourceType.PDF,
        source_uri=f"knowledge/risk/{doc_id}.pdf",
        current_version_id=current_version_id,
        status=status,
        permission_scope=PermissionScope.INTERNAL,
    )


def _build_version(
    *,
    version_id: str,
    doc_id: str,
    embedding_dim: int = 2,
    embedding_model: str = "deterministic-v1",
    status: DocumentVersionStatus = DocumentVersionStatus.ACTIVE,
) -> KnowledgeDocumentVersion:
    return KnowledgeDocumentVersion(
        version_id=version_id,
        doc_id=doc_id,
        kb_id="risk_domain_knowledge",
        version=version_id.removeprefix(f"{doc_id}_"),
        file_hash=f"sha256:{version_id}",
        file_uri=f"knowledge/risk/{doc_id}.pdf",
        parser_version="swxy-parser-v1",
        chunker_version="chunker-v1",
        embedding_model=embedding_model,
        embedding_dim=embedding_dim,
        index_name=None,
        status=status,
        latest_manifest_index_id=None,
        active_manifest_index_id=None,
        last_job_id=None,
    )


def _build_chunk(
    *,
    chunk_id: str,
    version_id: str,
    doc_id: str,
    content: str,
    content_hash: str,
    order: int,
) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=chunk_id,
        kb_id="risk_domain_knowledge",
        doc_id=doc_id,
        version_id=version_id,
        chunk_order=order,
        chunk_type="paragraph",
        section_title=f"{doc_id} section {order}",
        section_path=[f"{doc_id} guide", f"section {order}"],
        page_start=order,
        page_end=order,
        content=content,
        content_hash=content_hash,
        status=ChunkStatus.PENDING,
        permission_scope=PermissionScope.INTERNAL,
        source_type=SourceType.PDF,
        source_uri=f"knowledge/risk/{doc_id}.pdf",
        source_metadata={"doc_name": f"{doc_id}.pdf"},
    )


@pytest.fixture()
def retrieval_scope_data(auth_db):
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.id_factory import build_faiss_index_id
    from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeDocumentRepository
    from app.risk_knowledge.indexing.faiss_store import FaissIndexStore
    from app.risk_knowledge.indexing.schemas import FaissIndexManifestDraft
    from app.risk_knowledge.persistence.repositories import (
        SqlAlchemyFaissIndexRepository,
        SqlAlchemyKnowledgeChunkEmbeddingRepository,
        SqlAlchemyKnowledgeChunkRepository,
    )
    from app.risk_knowledge.persistence.service import KnowledgeChunkPersistenceService

    artifact_root = auth_db / "retrieval-faiss"
    provider = DeterministicRetrievalEmbeddingProvider(dimension=2)

    with AuthSessionLocal() as db:
        doc_repo = SqlAlchemyKnowledgeDocumentRepository(db)
        chunk_repo = SqlAlchemyKnowledgeChunkRepository(db)
        embedding_repo = SqlAlchemyKnowledgeChunkEmbeddingRepository(db)
        manifest_repo = SqlAlchemyFaissIndexRepository(db)

        guide_doc = doc_repo.create_document(_build_document(doc_id="risk_guide"))
        ops_doc = doc_repo.create_document(_build_document(doc_id="ops_guide"))

        guide_version = doc_repo.create_version(
            _build_version(version_id="risk_guide_v1", doc_id="risk_guide", status=DocumentVersionStatus.ACTIVE)
        )
        ops_version = doc_repo.create_version(
            _build_version(version_id="ops_guide_v1", doc_id="ops_guide", status=DocumentVersionStatus.ACTIVE)
        )

        guide_doc = doc_repo.update_document(guide_doc.model_copy(update={"current_version_id": guide_version.version_id}))
        ops_doc = doc_repo.update_document(ops_doc.model_copy(update={"current_version_id": ops_version.version_id}))

        guide_chunks = [
            _build_chunk(
                chunk_id="risk_guide_v1_chunk_000001",
                version_id=guide_version.version_id,
                doc_id=guide_doc.doc_id,
                content="loan risk warning signal",
                content_hash="sha256:guide-1",
                order=1,
            ),
            _build_chunk(
                chunk_id="risk_guide_v1_chunk_000002",
                version_id=guide_version.version_id,
                doc_id=guide_doc.doc_id,
                content="post-loan monitoring signal",
                content_hash="sha256:guide-2",
                order=2,
            ),
        ]
        ops_chunks = [
            _build_chunk(
                chunk_id="ops_guide_v1_chunk_000001",
                version_id=ops_version.version_id,
                doc_id=ops_doc.doc_id,
                content="collection strategy reminder",
                content_hash="sha256:ops-1",
                order=1,
            )
        ]
        KnowledgeChunkPersistenceService(db).persist_chunks(guide_version, guide_chunks)
        KnowledgeChunkPersistenceService(db).persist_chunks(ops_version, ops_chunks)

        all_chunk_records = chunk_repo.list_by_version(guide_version.version_id) + chunk_repo.list_by_version(ops_version.version_id)

        embeddings = provider.embed(
            [
                EmbeddingInput(
                    chunk_id=record.chunk_id,
                    content_hash=record.content_hash,
                    text=record.content_text,
                    input_type="document",
                )
                for record in all_chunk_records
            ]
        )
        embeddings_by_chunk = {item.chunk_id: item for item in embeddings}
        for record in all_chunk_records:
            embedding_repo.create_or_validate_idempotent(
                kb_id=record.kb_id,
                doc_id=record.doc_id,
                version_id=record.version_id,
                result=embeddings_by_chunk[record.chunk_id],
                embedding_id=f"emb_{record.chunk_id}",
            )

        store = FaissIndexStore(artifact_root=artifact_root, db=db)

        for version in (guide_version, ops_version):
            version_chunks = chunk_repo.list_by_version(version.version_id)
            version_embeddings = [
                embeddings_by_chunk[item.chunk_id]
                for item in version_chunks
            ]
            index_id = build_faiss_index_id(version.version_id, f"idxjob_{version.version_id}")
            built = store.build_index(
                version_embeddings,
                FaissIndexManifestDraft(
                    index_id=index_id,
                    kb_id=version.kb_id,
                    version_id=version.version_id,
                    embedding_provider="deterministic_test",
                    embedding_model="deterministic-v1",
                    embedding_dimension=2,
                    job_id=f"idxjob_{version.version_id}",
                    index_type="flat_l2",
                    distance_metric="l2",
                    chunk_content_pairs=[(item.chunk_id, item.content_hash) for item in version_embeddings],
                ),
            )
            saved = store.save_index(built)
            manifest_repo.activate_manifest(version_id=version.version_id, index_id=saved.manifest.index_id)
            stored_version = doc_repo.get_version(version.version_id)
            assert stored_version is not None
            doc_repo.update_version(
                stored_version.model_copy(
                    update={
                        "latest_manifest_index_id": saved.manifest.index_id,
                        "active_manifest_index_id": saved.manifest.index_id,
                        "status": DocumentVersionStatus.ACTIVE,
                    }
                )
            )
        db.commit()

    return {
        "artifact_root": artifact_root,
        "kb_id": "risk_domain_knowledge",
        "guide_doc_id": "risk_guide",
        "ops_doc_id": "ops_guide",
        "guide_version_id": "risk_guide_v1",
        "ops_version_id": "ops_guide_v1",
        "provider": provider,
    }
