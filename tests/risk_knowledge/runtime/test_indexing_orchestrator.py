from __future__ import annotations

from app.knowledge_base.schemas import IndexingJobTrigger


class DeterministicTestEmbeddingProvider:
    provider_name = "deterministic_test"

    def embed(self, inputs):
        from app.risk_knowledge.embedding.schemas import EmbeddingVectorResult

        return [
            EmbeddingVectorResult(
                chunk_id=item.chunk_id,
                content_hash=item.content_hash,
                provider=self.provider_name,
                model="deterministic-v1",
                dimension=2,
                vector=[float(len(item.text)), float(len(item.chunk_id))],
                vector_checksum=f"sha256:{len(item.text)}",
            )
            for item in inputs
        ]


def test_indexing_orchestrator_retry_preserves_lineage(
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
    from app.knowledge_base.schemas import IndexingJobStatus, KnowledgeIngestJob
    from app.risk_knowledge.runtime.orchestrator import IndexingOrchestrator

    with AuthSessionLocal() as db:
        doc_repo = SqlAlchemyKnowledgeDocumentRepository(db)
        job_repo = SqlAlchemyKnowledgeIngestJobRepository(db)
        doc_repo.create_document(sample_document)
        doc_repo.create_version(sample_version)
        failed_job = job_repo.create(
            KnowledgeIngestJob(
                job_id="idxjob_root",
                kb_id=sample_document.kb_id,
                doc_id=sample_document.doc_id,
                version_id=sample_version.version_id,
                status=IndexingJobStatus.FAILED,
                current_step="failed",
                error_message="provider timeout",
                trigger=IndexingJobTrigger.INITIAL_INDEX,
                attempt=1,
                max_attempts=3,
                root_job_id="idxjob_root",
                retry_of_job_id=None,
                started_at=None,
                completed_at=None,
                last_heartbeat_at=None,
                latest_manifest_index_id=None,
                active_manifest_index_id=None,
            )
        )
        db.commit()

    orchestrator = IndexingOrchestrator(
        redis_client=fake_redis_client,
        embedding_provider=DeterministicTestEmbeddingProvider(),
        artifact_root=tmp_path,
    )
    retry_result = orchestrator.start_retry(
        parsed_document=sample_parsed_document,
        document=sample_document,
        version=sample_version,
        failed_job_id=failed_job.job_id,
    )

    assert retry_result.retry_of_job_id == "idxjob_root"
    assert retry_result.root_job_id == "idxjob_root"
    assert retry_result.attempt == 2


def test_indexing_orchestrator_reuses_manifest_when_fingerprint_unchanged(
    auth_db,
    fake_redis_client,
    sample_document,
    sample_version,
    sample_parsed_document,
    tmp_path,
) -> None:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeDocumentRepository
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
    )
    first = orchestrator.start_initial_index(
        parsed_document=sample_parsed_document,
        document=sample_document,
        version=sample_version,
    )
    second = orchestrator.start_rebuild_from_persisted_chunks(
        document=sample_document,
        version=sample_version,
        force=False,
    )

    assert first.active_manifest_index_id == second.active_manifest_index_id
