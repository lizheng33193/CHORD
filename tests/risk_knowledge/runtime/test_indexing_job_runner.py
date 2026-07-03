from __future__ import annotations

import pytest

from app.knowledge_base.schemas import DocumentVersionStatus


class DeterministicTestEmbeddingProvider:
    provider_name = "deterministic_test"

    def embed(self, inputs):
        from app.risk_knowledge.embedding.schemas import EmbeddingVectorResult

        results = []
        for item in inputs:
            results.append(
                EmbeddingVectorResult(
                    chunk_id=item.chunk_id,
                    content_hash=item.content_hash,
                    provider=self.provider_name,
                    model="deterministic-v1",
                    dimension=2,
                    vector=[float(len(item.text)), float(len(item.chunk_id))],
                    vector_checksum=f"sha256:{len(item.text)}",
                )
            )
        return results


def test_indexing_job_runner_happy_path_persists_and_activates_manifest(
    auth_db,
    fake_redis_client,
    sample_document,
    sample_version,
    sample_parsed_document,
    tmp_path,
) -> None:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.repositories.sqlalchemy import (
        SqlAlchemyKnowledgeDocumentRepository,
        SqlAlchemyKnowledgeIngestJobRepository,
    )
    from app.knowledge_base.schemas import DocumentStatus
    from app.risk_knowledge.runtime.orchestrator import IndexingOrchestrator

    with AuthSessionLocal() as db:
        doc_repo = SqlAlchemyKnowledgeDocumentRepository(db)
        job_repo = SqlAlchemyKnowledgeIngestJobRepository(db)
        doc_repo.create_document(sample_document)
        doc_repo.create_version(sample_version)
        db.commit()

    orchestrator = IndexingOrchestrator(
        redis_client=fake_redis_client,
        embedding_provider=DeterministicTestEmbeddingProvider(),
        artifact_root=tmp_path,
    )
    result = orchestrator.start_initial_index(
        parsed_document=sample_parsed_document,
        document=sample_document,
        version=sample_version,
    )

    with AuthSessionLocal() as db:
        doc_repo = SqlAlchemyKnowledgeDocumentRepository(db)
        job_repo = SqlAlchemyKnowledgeIngestJobRepository(db)
        stored_version = doc_repo.get_version(sample_version.version_id)
        stored_document = doc_repo.get_document(sample_document.doc_id)
        stored_job = job_repo.get(result.job_id)

        assert stored_version is not None
        assert stored_version.status == DocumentVersionStatus.ACTIVE
        assert stored_version.active_manifest_index_id is not None
        assert stored_document is not None
        assert stored_document.status == DocumentStatus.ACTIVE
        assert stored_job is not None
        assert stored_job.active_manifest_index_id == stored_version.active_manifest_index_id


def test_indexing_job_runner_lost_lock_blocks_manifest_activation(
    auth_db,
    fake_redis_client,
    sample_document,
    sample_version,
    sample_parsed_document,
    tmp_path,
) -> None:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeDocumentRepository
    from app.risk_knowledge.runtime.errors import IndexingLockLostError
    from app.risk_knowledge.runtime.orchestrator import IndexingOrchestrator

    with AuthSessionLocal() as db:
        doc_repo = SqlAlchemyKnowledgeDocumentRepository(db)
        doc_repo.create_document(sample_document)
        doc_repo.create_version(sample_version)
        db.commit()

    orchestrator = IndexingOrchestrator(
        redis_client=fake_redis_client,
        embedding_provider=DeterministicTestEmbeddingProvider(),
        artifact_root=tmp_path,
        lose_lock_before_activation=True,
    )

    with pytest.raises(IndexingLockLostError):
        orchestrator.start_initial_index(
            parsed_document=sample_parsed_document,
            document=sample_document,
            version=sample_version,
        )


def test_indexing_job_runner_fails_on_chunk_guard_before_embedding(
    auth_db,
    fake_redis_client,
    sample_document,
    sample_version,
    sample_parsed_document,
    tmp_path,
    monkeypatch,
) -> None:
    from app.auth.database import AuthSessionLocal
    from app.core.config import settings
    from app.knowledge_base.repositories.sqlalchemy import (
        SqlAlchemyKnowledgeDocumentRepository,
        SqlAlchemyKnowledgeIngestJobRepository,
        SqlAlchemyKnowledgeIngestJobRuntimeStateRepository,
    )
    from app.knowledge_base.schemas import IndexingJobStatus
    from app.risk_knowledge.runtime.orchestrator import IndexingOrchestrator

    monkeypatch.setattr(settings, "risk_knowledge_indexing_max_chunk_count", 1, raising=False)

    with AuthSessionLocal() as db:
        doc_repo = SqlAlchemyKnowledgeDocumentRepository(db)
        doc_repo.create_document(sample_document)
        doc_repo.create_version(sample_version)
        db.commit()

    orchestrator = IndexingOrchestrator(
        redis_client=fake_redis_client,
        embedding_provider=DeterministicTestEmbeddingProvider(),
        artifact_root=tmp_path,
    )

    with pytest.raises(Exception):
        orchestrator.start_initial_index(
            parsed_document=sample_parsed_document,
            document=sample_document,
            version=sample_version,
            job_id="idxjob_chunk_guard",
        )

    with AuthSessionLocal() as db:
        job = SqlAlchemyKnowledgeIngestJobRepository(db).get("idxjob_chunk_guard")
        runtime = SqlAlchemyKnowledgeIngestJobRuntimeStateRepository(db).get("idxjob_chunk_guard")

        assert job is not None
        assert job.status == IndexingJobStatus.FAILED
        assert "chunk" in (job.error_message or "").lower()
        assert runtime is not None
        assert "failed during" in (runtime.progress_message or "")


def test_indexing_job_runner_fails_on_embedding_batch_guard_before_provider_call(
    auth_db,
    fake_redis_client,
    sample_document,
    sample_version,
    sample_parsed_document,
    tmp_path,
    monkeypatch,
) -> None:
    from app.auth.database import AuthSessionLocal
    from app.core.config import settings
    from app.knowledge_base.repositories.sqlalchemy import (
        SqlAlchemyKnowledgeDocumentRepository,
        SqlAlchemyKnowledgeIngestJobRepository,
    )
    from app.knowledge_base.schemas import IndexingJobStatus
    from app.risk_knowledge.runtime.orchestrator import IndexingOrchestrator

    calls: list[int] = []

    class CountingProvider(DeterministicTestEmbeddingProvider):
        max_batch_size = 1

        def embed(self, inputs):
            calls.append(len(inputs))
            return super().embed(inputs)

    monkeypatch.setattr(settings, "risk_knowledge_indexing_max_embedding_batches", 1, raising=False)

    with AuthSessionLocal() as db:
        doc_repo = SqlAlchemyKnowledgeDocumentRepository(db)
        doc_repo.create_document(sample_document)
        doc_repo.create_version(sample_version)
        db.commit()

    orchestrator = IndexingOrchestrator(
        redis_client=fake_redis_client,
        embedding_provider=CountingProvider(),
        artifact_root=tmp_path,
    )

    with pytest.raises(Exception):
        orchestrator.start_initial_index(
            parsed_document=sample_parsed_document,
            document=sample_document,
            version=sample_version,
            job_id="idxjob_batch_guard",
        )

    with AuthSessionLocal() as db:
        job = SqlAlchemyKnowledgeIngestJobRepository(db).get("idxjob_batch_guard")
        assert job is not None
        assert job.status == IndexingJobStatus.FAILED
        assert "batch" in (job.error_message or "").lower()
        assert calls == []


def test_indexing_job_runner_fails_on_runtime_guard(
    auth_db,
    fake_redis_client,
    sample_document,
    sample_version,
    sample_parsed_document,
    tmp_path,
    monkeypatch,
) -> None:
    from app.auth.database import AuthSessionLocal
    from app.core.config import settings
    from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeDocumentRepository, SqlAlchemyKnowledgeIngestJobRepository
    from app.knowledge_base.schemas import IndexingJobStatus
    from app.risk_knowledge.runtime.orchestrator import IndexingOrchestrator

    monkeypatch.setattr(settings, "risk_knowledge_indexing_max_runtime_seconds", 0, raising=False)

    with AuthSessionLocal() as db:
        doc_repo = SqlAlchemyKnowledgeDocumentRepository(db)
        doc_repo.create_document(sample_document)
        doc_repo.create_version(sample_version)
        db.commit()

    orchestrator = IndexingOrchestrator(
        redis_client=fake_redis_client,
        embedding_provider=DeterministicTestEmbeddingProvider(),
        artifact_root=tmp_path,
    )

    with pytest.raises(Exception):
        orchestrator.start_initial_index(
            parsed_document=sample_parsed_document,
            document=sample_document,
            version=sample_version,
            job_id="idxjob_runtime_guard",
        )

    with AuthSessionLocal() as db:
        job = SqlAlchemyKnowledgeIngestJobRepository(db).get("idxjob_runtime_guard")
        assert job is not None
        assert job.status == IndexingJobStatus.FAILED
        assert "runtime" in (job.error_message or "").lower()
