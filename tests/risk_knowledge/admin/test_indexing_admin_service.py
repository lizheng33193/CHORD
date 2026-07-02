from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest


def _seed_version(
    tmp_path: Path,
    *,
    version_status="parsed",
    current_version_id: str | None = None,
    latest_manifest_index_id: str | None = None,
    active_manifest_index_id: str | None = None,
    last_job_id: str | None = None,
    source_type: str = "txt",
    filename: str | None = None,
) -> tuple[str, str]:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.repositories.sqlalchemy import (
        SqlAlchemyKnowledgeBaseRepository,
        SqlAlchemyKnowledgeDocumentRepository,
    )
    from app.knowledge_base.schemas import (
        DocumentStatus,
        DocumentVersionStatus,
        KnowledgeBase,
        KnowledgeBaseStatus,
        KnowledgeBaseType,
        KnowledgeDocument,
        KnowledgeDocumentVersion,
        PermissionScope,
        SourceType,
    )

    resolved_source_type = SourceType(source_type)
    resolved_filename = filename or f"risk-guide.{resolved_source_type.value}"
    file_path = tmp_path / resolved_filename
    file_path.write_text("risk knowledge body", encoding="utf-8")

    with AuthSessionLocal() as db:
        kb_repo = SqlAlchemyKnowledgeBaseRepository(db)
        doc_repo = SqlAlchemyKnowledgeDocumentRepository(db)
        kb_repo.create(
            KnowledgeBase(
                kb_id="risk_domain_knowledge",
                kb_name="风控领域知识库",
                kb_type=KnowledgeBaseType.RISK_DOMAIN,
                description="用于画像解释的风控知识资料",
                status=KnowledgeBaseStatus.ACTIVE,
                index_alias="risk_domain_knowledge_active",
            )
        )
        doc_repo.create_document(
            KnowledgeDocument(
                doc_id="risk_guide",
                kb_id="risk_domain_knowledge",
                doc_title="智能风控指南",
                doc_name=resolved_filename,
                source_type=resolved_source_type,
                source_uri=str(file_path),
                current_version_id=current_version_id,
                status=DocumentStatus.ACTIVE if current_version_id else DocumentStatus.INACTIVE,
                permission_scope=PermissionScope.INTERNAL,
            )
        )
        doc_repo.create_version(
            KnowledgeDocumentVersion(
                version_id="risk_guide_v1",
                doc_id="risk_guide",
                kb_id="risk_domain_knowledge",
                version="v1",
                file_hash="sha256:test",
                file_uri=str(file_path),
                parser_version="swxy-parser-v1",
                chunker_version="chunker-v1",
                embedding_model="deterministic-v1",
                embedding_dim=2,
                index_name=None,
                status=DocumentVersionStatus(version_status),
                latest_manifest_index_id=latest_manifest_index_id,
                active_manifest_index_id=active_manifest_index_id,
                last_job_id=last_job_id,
            )
        )
        db.commit()
    return "risk_guide", "risk_guide_v1"


def _seed_job(
    *,
    job_id: str,
    status: str,
    trigger: str = "initial_index",
    attempt: int = 1,
    root_job_id: str | None = None,
    retry_of_job_id: str | None = None,
) -> None:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeIngestJobRepository
    from app.knowledge_base.schemas import IndexingJobTrigger, IngestStep, KnowledgeIngestJob

    with AuthSessionLocal() as db:
        SqlAlchemyKnowledgeIngestJobRepository(db).create(
            KnowledgeIngestJob(
                job_id=job_id,
                kb_id="risk_domain_knowledge",
                doc_id="risk_guide",
                version_id="risk_guide_v1",
                status=status,
                current_step=IngestStep.FAILED if status == "failed" else IngestStep.QUEUED,
                error_message="boom" if status == "failed" else None,
                trigger=IndexingJobTrigger(trigger),
                attempt=attempt,
                max_attempts=3,
                root_job_id=root_job_id or job_id,
                retry_of_job_id=retry_of_job_id,
                started_at=datetime.now(UTC).replace(tzinfo=None),
                completed_at=None,
                last_heartbeat_at=None,
                latest_manifest_index_id=None,
                active_manifest_index_id=None,
            )
        )
        db.commit()


def _seed_manifest(index_id: str, *, active: bool = True) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.indexing.schemas import FaissIndexManifest
    from app.risk_knowledge.persistence.repositories import SqlAlchemyFaissIndexRepository

    with AuthSessionLocal() as db:
        SqlAlchemyFaissIndexRepository(db).save_manifest(
            FaissIndexManifest(
                index_id=index_id,
                kb_id="risk_domain_knowledge",
                version_id="risk_guide_v1",
                embedding_provider="deterministic_test",
                embedding_model="deterministic-v1",
                embedding_dimension=2,
                job_id="idxjob_existing",
                index_type="flat_l2",
                distance_metric="l2",
                record_count=1,
                artifact_path="/tmp/fake.index",
                mapping_path="/tmp/fake.mapping.json",
                checksum="sha256:manifest",
                build_fingerprint="sha256:fingerprint",
                build_status="active" if active else "built",
                is_active=active,
                superseded_by_index_id=None,
                superseded_at=None,
                built_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        db.commit()


def test_indexing_service_index_returns_new_job_metadata_immediately(auth_db, tmp_path, fake_redis_client) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService

    _seed_version(tmp_path)

    with AuthSessionLocal() as db:
        service = IndexingAdminService(
            db,
            redis_client=fake_redis_client,
            embedding_provider=None,
            job_launcher=lambda task: None,
        )
        launched = service.start_index("risk_guide_v1")

        assert launched.result == "accepted"
        assert launched.job_id is not None
        assert launched.status == "pending"
        stored = service.get_job(launched.job_id)
        assert stored.job_id == launched.job_id
        assert stored.runtime_state_available is False


def test_indexing_service_index_returns_existing_pending_job(auth_db, tmp_path, fake_redis_client) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService

    _seed_version(tmp_path)
    _seed_job(job_id="idxjob_existing", status="pending")

    with AuthSessionLocal() as db:
        service = IndexingAdminService(db, redis_client=fake_redis_client, job_launcher=lambda task: None)
        launched = service.start_index("risk_guide_v1")

        assert launched.result == "existing_job"
        assert launched.job_id == "idxjob_existing"


def test_indexing_service_index_returns_already_indexed_when_manifest_is_active(auth_db, tmp_path, fake_redis_client) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService

    _seed_version(
        tmp_path,
        version_status="active",
        current_version_id="risk_guide_v1",
        latest_manifest_index_id="idx_manifest_active",
        active_manifest_index_id="idx_manifest_active",
        last_job_id="idxjob_existing",
    )
    _seed_manifest("idx_manifest_active", active=True)

    with AuthSessionLocal() as db:
        service = IndexingAdminService(db, redis_client=fake_redis_client, job_launcher=lambda task: None)
        launched = service.start_index("risk_guide_v1")

        assert launched.result == "already_indexed"
        assert launched.job_id == "idxjob_existing"
        assert launched.active_manifest_index_id == "idx_manifest_active"


def test_indexing_service_rebuild_returns_new_job_metadata_immediately(auth_db, tmp_path, fake_redis_client) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService

    _seed_version(tmp_path, version_status="failed")

    with AuthSessionLocal() as db:
        service = IndexingAdminService(db, redis_client=fake_redis_client, job_launcher=lambda task: None)
        launched = service.start_rebuild("risk_guide_v1")

        assert launched.result == "accepted"
        assert launched.trigger == "rebuild_from_parsed"


def test_indexing_service_retry_failed_job_preserves_lineage(auth_db, tmp_path, fake_redis_client) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService

    _seed_version(tmp_path, version_status="failed", last_job_id="idxjob_root")
    _seed_job(job_id="idxjob_root", status="failed")

    with AuthSessionLocal() as db:
        service = IndexingAdminService(db, redis_client=fake_redis_client, job_launcher=lambda task: None)
        launched = service.retry_job("idxjob_root")
        summary = service.get_job(launched.job_id)

        assert launched.result == "accepted"
        assert launched.trigger == "retry"
        assert summary.retry_of_job_id == "idxjob_root"
        assert summary.root_job_id == "idxjob_root"
        assert summary.attempt == 2


def test_indexing_service_retry_rejects_when_running_job_exists(auth_db, tmp_path, fake_redis_client) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.admin.errors import RunningIndexingJobConflictAdminError
    from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService

    _seed_version(tmp_path, version_status="failed", last_job_id="idxjob_root")
    _seed_job(job_id="idxjob_root", status="failed")
    _seed_job(job_id="idxjob_pending", status="pending")

    with AuthSessionLocal() as db:
        service = IndexingAdminService(db, redis_client=fake_redis_client, job_launcher=lambda task: None)
        with pytest.raises(RunningIndexingJobConflictAdminError):
            service.retry_job("idxjob_root")


def test_indexing_service_job_summary_survives_missing_redis_state(auth_db, tmp_path) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService

    class BrokenRedisClient:
        def get(self, *_args, **_kwargs):
            raise RuntimeError("redis unavailable")

        def set(self, *_args, **_kwargs):
            raise RuntimeError("redis unavailable")

    _seed_version(tmp_path)
    _seed_job(job_id="idxjob_existing", status="pending")

    with AuthSessionLocal() as db:
        service = IndexingAdminService(db, redis_client=BrokenRedisClient(), job_launcher=lambda task: None)
        summary = service.get_job("idxjob_existing")

        assert summary.job_id == "idxjob_existing"
        assert summary.runtime_state_available is False


def test_indexing_service_job_summary_falls_back_to_durable_runtime_state(auth_db, tmp_path) -> None:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeIngestJobRuntimeStateRepository
    from app.knowledge_base.schemas import KnowledgeIngestJobRuntimeState
    from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService

    class BrokenRedisClient:
        def get(self, *_args, **_kwargs):
            raise RuntimeError("redis unavailable")

        def set(self, *_args, **_kwargs):
            raise RuntimeError("redis unavailable")

    _seed_version(tmp_path)
    _seed_job(job_id="idxjob_existing", status="failed")

    with AuthSessionLocal() as db:
        SqlAlchemyKnowledgeIngestJobRuntimeStateRepository(db).upsert(
            KnowledgeIngestJobRuntimeState(
                job_id="idxjob_existing",
                progress_message="failed during embedding: provider timeout",
                progress_completed_steps=6,
                progress_total_steps=10,
                chunk_count=1139,
                embedding_count=1100,
                embedding_batch_count=114,
                embedding_batches_completed=110,
                vector_mapping_count=None,
                parser_duration_ms=120000,
                embedding_duration_ms=330000,
                faiss_duration_ms=None,
                total_duration_ms=500000,
            )
        )
        db.commit()

    with AuthSessionLocal() as db:
        service = IndexingAdminService(db, redis_client=BrokenRedisClient(), job_launcher=lambda task: None)
        summary = service.get_job("idxjob_existing")

        assert summary.runtime_state_available is False
        assert summary.progress_message == "failed during embedding: provider timeout"
        assert summary.chunk_count == 1139
        assert summary.embedding_batches_completed == 110
        assert summary.total_duration_ms == 500000


def test_indexing_service_page_count_propagates_from_parser_metadata(auth_db, tmp_path, fake_redis_client) -> None:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeIngestJobRuntimeStateRepository
    from app.knowledge_base.schemas import SourceType
    from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService
    from app.risk_knowledge.ingestion.schemas import ParsedDocument, RawParsedChunk, SourceDocumentRef

    class ParserWithPageCount:
        def parse(self, context, *, progress_callback=None):
            if progress_callback is not None:
                progress_callback(None, "OCR started")
            return ParsedDocument(
                source=SourceDocumentRef(
                    kb_id=context.kb_id,
                    doc_id=context.doc_id,
                    version_id=context.version_id,
                    file_path=context.file_path,
                    doc_name=context.doc_name,
                    source_type=SourceType.PDF,
                ),
                parser_name="stub-parser",
                parser_version="stub-v1",
                raw_chunks=[
                    RawParsedChunk(
                        chunk_order=1,
                        raw_content="风险知识内容",
                        chunk_type="paragraph",
                        source_metadata={},
                    )
                ],
                document_metadata={"page_count": 253},
            )

    class NoopOrchestrator:
        def start_initial_index(self, **_kwargs):
            return None

    _seed_version(tmp_path, source_type="pdf", filename="risk-guide.pdf")

    with AuthSessionLocal() as db:
        service = IndexingAdminService(
            db,
            parser_adapter=ParserWithPageCount(),
            redis_client=fake_redis_client,
            job_launcher=lambda task: task(),
            orchestrator_factory=lambda _redis, _embedding: NoopOrchestrator(),
        )
        launched = service.start_index("risk_guide_v1")
        summary = service.get_job(launched.job_id)
        durable_runtime = SqlAlchemyKnowledgeIngestJobRuntimeStateRepository(db).get(launched.job_id)

        assert durable_runtime is not None
        assert durable_runtime.page_count == 253
        assert summary.page_count == 253


def test_indexing_service_parser_failure_marks_durable_job_failed(auth_db, tmp_path, fake_redis_client) -> None:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeIngestJobRuntimeStateRepository
    from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService

    class FailingParser:
        def parse(self, _context, *, progress_callback=None):
            raise RuntimeError("parser exploded before runner")

    _seed_version(tmp_path, source_type="pdf", filename="risk-guide.pdf")

    with AuthSessionLocal() as db:
        service = IndexingAdminService(
            db,
            parser_adapter=FailingParser(),
            redis_client=fake_redis_client,
            job_launcher=lambda task: task(),
        )
        launched = service.start_index("risk_guide_v1")
        summary = service.get_job(launched.job_id)
        durable_runtime = SqlAlchemyKnowledgeIngestJobRuntimeStateRepository(db).get(launched.job_id)

        assert summary.status == "failed"
        assert summary.current_step == "parsing_pdf"
        assert summary.runtime_status == "failed"
        assert summary.runtime_current_step == "parsing_pdf"
        assert summary.error_message == "parser exploded before runner"
        assert summary.progress_message == "failed during parsing_pdf: parser exploded before runner"
        assert summary.completed_at is not None
        assert summary.last_heartbeat_at is not None
        assert durable_runtime is not None
        assert durable_runtime.progress_message == "failed during parsing_pdf: parser exploded before runner"


def test_indexing_service_activate_is_idempotent_for_same_manifest(auth_db, tmp_path, fake_redis_client) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService

    _seed_version(
        tmp_path,
        version_status="active",
        current_version_id="risk_guide_v1",
        latest_manifest_index_id="idx_manifest_active",
        active_manifest_index_id="idx_manifest_active",
        last_job_id="idxjob_existing",
    )
    _seed_manifest("idx_manifest_active", active=True)

    with AuthSessionLocal() as db:
        service = IndexingAdminService(db, redis_client=fake_redis_client, job_launcher=lambda task: None)
        result = service.activate_version("risk_guide_v1", manifest_index_id="idx_manifest_active")

        assert result.result == "already_active"
        assert result.manifest_index_id == "idx_manifest_active"
