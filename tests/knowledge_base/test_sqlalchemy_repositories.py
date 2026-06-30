from __future__ import annotations

from pathlib import Path

import pytest

from app.knowledge_base.schemas import (
    DocumentStatus,
    DocumentVersionStatus,
    IndexingJobStatus,
    IndexingJobTrigger,
    PermissionScope,
    SourceType,
)


@pytest.fixture()
def auth_db(tmp_path: Path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "auth_database_url", f"sqlite:///{tmp_path / 'auth.sqlite3'}", raising=False)
    monkeypatch.setattr(settings, "auth_jwt_secret", "test-secret-for-m2d9", raising=False)
    monkeypatch.setattr(settings, "default_admin_username", "admin", raising=False)
    monkeypatch.setattr(settings, "default_admin_email", "admin@example.com", raising=False)
    monkeypatch.setattr(settings, "default_admin_password", "admin123456", raising=False)

    from app.auth.database import AuthSessionLocal, create_auth_schema, reset_auth_engine
    from app.auth.seed import seed_auth_data

    reset_auth_engine()
    create_auth_schema()
    with AuthSessionLocal() as db:
        seed_auth_data(db)

    yield

    reset_auth_engine()


def test_sqlalchemy_document_version_and_job_repositories_persist_durable_fields(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.repositories.sqlalchemy import (
        SqlAlchemyKnowledgeDocumentRepository,
        SqlAlchemyKnowledgeIngestJobRepository,
    )
    from app.knowledge_base.schemas import KnowledgeDocument, KnowledgeDocumentVersion, KnowledgeIngestJob

    with AuthSessionLocal() as db:
        document_repo = SqlAlchemyKnowledgeDocumentRepository(db)
        job_repo = SqlAlchemyKnowledgeIngestJobRepository(db)

        document = document_repo.create_document(
            KnowledgeDocument(
                doc_id="risk_guide",
                kb_id="risk_domain_knowledge",
                doc_title="智能风控指南",
                doc_name="risk_guide.pdf",
                source_type=SourceType.PDF,
                source_uri="knowledge/risk/risk_guide.pdf",
                current_version_id=None,
                status=DocumentStatus.INACTIVE,
                permission_scope=PermissionScope.INTERNAL,
            )
        )
        version = document_repo.create_version(
            KnowledgeDocumentVersion(
                version_id="risk_guide_202607",
                doc_id=document.doc_id,
                kb_id=document.kb_id,
                version="2026-07",
                file_hash="sha256:file",
                file_uri="knowledge/risk/risk_guide.pdf",
                parser_version="swxy-parser-v1",
                chunker_version="chunker-v1",
                embedding_model="deterministic-v1",
                embedding_dim=2,
                index_name=None,
                status=DocumentVersionStatus.PARSED,
                latest_manifest_index_id="idx_risk_guide_202607",
                active_manifest_index_id=None,
                last_job_id="idxjob_root",
            )
        )
        job = job_repo.create(
            KnowledgeIngestJob(
                job_id="idxjob_root",
                kb_id=document.kb_id,
                doc_id=document.doc_id,
                version_id=version.version_id,
                status=IndexingJobStatus.PENDING,
                current_step="queued",
                error_message=None,
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

        stored_version = document_repo.get_version(version.version_id)
        stored_jobs = job_repo.list_by_version(version.version_id)

        assert stored_version is not None
        assert stored_version.latest_manifest_index_id == "idx_risk_guide_202607"
        assert stored_version.last_job_id == "idxjob_root"
        assert len(stored_jobs) == 1
        assert stored_jobs[0].status == IndexingJobStatus.PENDING
        assert stored_jobs[0].trigger == IndexingJobTrigger.INITIAL_INDEX


def test_sqlalchemy_job_repository_tracks_retry_lineage(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeIngestJobRepository
    from app.knowledge_base.schemas import KnowledgeIngestJob

    with AuthSessionLocal() as db:
        job_repo = SqlAlchemyKnowledgeIngestJobRepository(db)
        original = job_repo.create(
            KnowledgeIngestJob(
                job_id="idxjob_root",
                kb_id="risk_domain_knowledge",
                doc_id="risk_guide",
                version_id="risk_guide_202607",
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
        retry = job_repo.create(
            KnowledgeIngestJob(
                job_id="idxjob_retry_2",
                kb_id="risk_domain_knowledge",
                doc_id="risk_guide",
                version_id="risk_guide_202607",
                status=IndexingJobStatus.PENDING,
                current_step="queued",
                error_message=None,
                trigger=IndexingJobTrigger.RETRY,
                attempt=2,
                max_attempts=3,
                root_job_id=original.root_job_id,
                retry_of_job_id=original.job_id,
                started_at=None,
                completed_at=None,
                last_heartbeat_at=None,
                latest_manifest_index_id=None,
                active_manifest_index_id=None,
            )
        )
        db.commit()

        stored = job_repo.list_by_version("risk_guide_202607")
        assert [item.job_id for item in stored] == ["idxjob_retry_2", "idxjob_root"]
        assert retry.retry_of_job_id == "idxjob_root"
        assert retry.root_job_id == "idxjob_root"
