from __future__ import annotations

from datetime import UTC, datetime
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
        assert stored_jobs[0].status == IndexingJobStatus.QUEUED
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


def test_sqlalchemy_runtime_state_repository_persists_observability_fields(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeIngestJobRuntimeStateRepository
    from app.knowledge_base.schemas import KnowledgeIngestJobRuntimeState

    with AuthSessionLocal() as db:
        runtime_repo = SqlAlchemyKnowledgeIngestJobRuntimeStateRepository(db)
        created = runtime_repo.upsert(
            KnowledgeIngestJobRuntimeState(
                job_id="idxjob_root",
                progress_message="embedding batch 31 / 114",
                progress_completed_steps=6,
                progress_total_steps=10,
                file_size_bytes=26482250,
                page_count=253,
                chunk_count=1139,
                embedding_count=1139,
                embedding_batch_count=114,
                embedding_batches_completed=31,
                vector_mapping_count=1139,
                parser_duration_ms=120000,
                embedding_duration_ms=330000,
                faiss_duration_ms=18000,
                total_duration_ms=612000,
            )
        )
        db.commit()

        fetched = runtime_repo.get("idxjob_root")

        assert created.job_id == "idxjob_root"
        assert fetched is not None
        assert fetched.progress_message == "embedding batch 31 / 114"
        assert fetched.page_count == 253
        assert fetched.vector_mapping_count == 1139


def test_sqlalchemy_job_control_repository_persists_lease_and_stale_fields(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeIngestJobControlRepository
    from app.knowledge_base.schemas import KnowledgeIngestJobControl

    lease_expires_at = datetime(2026, 7, 2, 12, 0, 0)
    cancel_requested_at = datetime(2026, 7, 2, 12, 1, 0)
    stale_detected_at = datetime(2026, 7, 2, 12, 2, 0)

    with AuthSessionLocal() as db:
        control_repo = SqlAlchemyKnowledgeIngestJobControlRepository(db)
        created = control_repo.upsert(
            KnowledgeIngestJobControl(
                job_id="idxjob_root",
                lease_owner="worker-a",
                lease_expires_at=lease_expires_at,
                cancel_requested_at=cancel_requested_at,
                stale_detected_at=stale_detected_at,
                stale_reason="lease expired",
            )
        )
        db.commit()

        fetched = control_repo.get("idxjob_root")

        assert created.job_id == "idxjob_root"
        assert fetched is not None
        assert fetched.lease_owner == "worker-a"
        assert fetched.lease_expires_at == lease_expires_at
        assert fetched.cancel_requested_at == cancel_requested_at
        assert fetched.stale_detected_at == stale_detected_at
        assert fetched.stale_reason == "lease expired"


def test_sqlalchemy_job_artifact_repository_tracks_cleanup_state(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeIngestArtifactRepository
    from app.knowledge_base.schemas import KnowledgeIngestArtifact

    created_at = datetime.now(UTC).replace(tzinfo=None)
    cleaned_at = datetime(2026, 7, 2, 12, 30, 0)

    with AuthSessionLocal() as db:
        artifact_repo = SqlAlchemyKnowledgeIngestArtifactRepository(db)
        artifact_repo.create(
            KnowledgeIngestArtifact(
                job_id="idxjob_root",
                version_id="risk_guide_202607",
                artifact_kind="faiss_index",
                artifact_path="outputs/risk_knowledge/faiss/idxjob_root.faiss",
                is_temporary=False,
                created_at=created_at,
                cleaned_at=None,
            )
        )
        artifact_repo.create(
            KnowledgeIngestArtifact(
                job_id="idxjob_root",
                version_id="risk_guide_202607",
                artifact_kind="temp_output",
                artifact_path="outputs/risk_knowledge/tmp/idxjob_root.partial",
                is_temporary=True,
                created_at=created_at,
                cleaned_at=cleaned_at,
            )
        )
        db.commit()

        artifacts = artifact_repo.list_by_job("idxjob_root")

        assert len(artifacts) == 2
        assert artifacts[0].artifact_kind == "faiss_index"
        assert artifacts[0].cleaned_at is None
        assert artifacts[1].artifact_kind == "temp_output"
        assert artifacts[1].is_temporary is True
        assert artifacts[1].cleaned_at == cleaned_at


def test_sqlalchemy_knowledge_base_repository_persists_kb_records(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeBaseRepository
    from app.knowledge_base.schemas import KnowledgeBase, KnowledgeBaseStatus, KnowledgeBaseType

    with AuthSessionLocal() as db:
        kb_repo = SqlAlchemyKnowledgeBaseRepository(db)
        created = kb_repo.create(
            KnowledgeBase(
                kb_id="risk_domain_knowledge",
                kb_name="风控领域知识库",
                kb_type=KnowledgeBaseType.RISK_DOMAIN,
                description="Risk-domain document knowledge base for M2D.",
                status=KnowledgeBaseStatus.ACTIVE,
                index_alias="chord_m2d_risk_knowledge_active",
            )
        )
        db.commit()

        fetched = kb_repo.get(created.kb_id)
        listed = kb_repo.list()

        assert fetched is not None
        assert fetched.kb_name == "风控领域知识库"
        assert fetched.index_alias == "chord_m2d_risk_knowledge_active"
        assert [item.kb_id for item in listed] == ["risk_domain_knowledge"]
