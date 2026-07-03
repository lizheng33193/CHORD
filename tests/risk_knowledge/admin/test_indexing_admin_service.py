from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
    filename: str = "risk-guide.txt",
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
    file_path = tmp_path / filename
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
                doc_name=filename,
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
        assert launched.status == "queued"
        stored = service.get_job(launched.job_id)
        assert stored.job_id == launched.job_id
        assert stored.runtime_state_available is False


def test_indexing_service_index_returns_existing_pending_job(auth_db, tmp_path, fake_redis_client) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService

    _seed_version(tmp_path)
    _seed_job(job_id="idxjob_existing", status="queued")

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
    _seed_job(job_id="idxjob_pending", status="queued")

    with AuthSessionLocal() as db:
        service = IndexingAdminService(db, redis_client=fake_redis_client, job_launcher=lambda task: None)
        with pytest.raises(RunningIndexingJobConflictAdminError):
            service.retry_job("idxjob_root")


def test_indexing_service_cancel_queued_job_marks_canceled(auth_db, tmp_path, fake_redis_client) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService

    _seed_version(tmp_path, last_job_id="idxjob_existing")
    _seed_job(job_id="idxjob_existing", status="queued")

    with AuthSessionLocal() as db:
        service = IndexingAdminService(db, redis_client=fake_redis_client, job_launcher=lambda task: None)
        result = service.cancel_job("idxjob_existing")
        summary = service.get_job("idxjob_existing")

        assert result.result == "canceled"
        assert result.job_id == "idxjob_existing"
        assert summary.status == "canceled"


def test_indexing_service_cancel_running_job_sets_cancel_requested(auth_db, tmp_path, fake_redis_client) -> None:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeIngestJobControlRepository
    from app.knowledge_base.schemas import KnowledgeIngestJobControl
    from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService

    _seed_version(tmp_path, version_status="indexing", last_job_id="idxjob_running")
    _seed_job(job_id="idxjob_running", status="running")

    with AuthSessionLocal() as db:
        SqlAlchemyKnowledgeIngestJobControlRepository(db).upsert(
            KnowledgeIngestJobControl(
                job_id="idxjob_running",
                lease_owner="worker-a",
                lease_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=30),
            )
        )
        db.commit()

    with AuthSessionLocal() as db:
        service = IndexingAdminService(db, redis_client=fake_redis_client, job_launcher=lambda task: None)
        result = service.cancel_job("idxjob_running")
        summary = service.get_job("idxjob_running")

        assert result.result == "cancel_requested"
        assert summary.status == "running"
        assert summary.cancel_requested_at is not None


def test_indexing_service_execute_job_fails_on_file_size_guard_before_parser(
    auth_db,
    tmp_path,
    fake_redis_client,
    monkeypatch,
) -> None:
    from app.auth.database import AuthSessionLocal
    from app.core.config import settings
    from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService

    parser_calls: list[str] = []

    class StubParser:
        def parse(self, *_args, **_kwargs):
            parser_calls.append("parse")
            raise AssertionError("parser should not be called when file size guard fails")

    monkeypatch.setattr(settings, "risk_knowledge_indexing_max_file_size_bytes", 1, raising=False)

    _seed_version(tmp_path, filename="oversized.txt")

    with AuthSessionLocal() as db:
        service = IndexingAdminService(
            db,
            parser_adapter=StubParser(),
            redis_client=fake_redis_client,
            job_launcher=lambda task: None,
        )
        launched = service.start_index("risk_guide_v1")

    with AuthSessionLocal() as db:
        service = IndexingAdminService(
            db,
            parser_adapter=StubParser(),
            redis_client=fake_redis_client,
            job_launcher=lambda task: None,
        )
        service.execute_job(launched.job_id)

    with AuthSessionLocal() as db:
        summary = IndexingAdminService(
            db,
            parser_adapter=StubParser(),
            redis_client=fake_redis_client,
            job_launcher=lambda task: None,
        ).get_job(launched.job_id)

        assert summary.status == "failed"
        assert "file" in (summary.error_message or "").lower()
        assert parser_calls == []


def test_indexing_service_execute_job_fails_on_page_count_guard_after_parser(
    auth_db,
    tmp_path,
    fake_redis_client,
    monkeypatch,
) -> None:
    from app.auth.database import AuthSessionLocal
    from app.core.config import settings
    from app.knowledge_base.schemas import SourceType
    from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService
    from app.risk_knowledge.ingestion.schemas import ParsedDocument, RawParsedChunk, SourceDocumentRef

    parser_calls: list[str] = []

    class StubParser:
        def parse(self, *_args, **_kwargs):
            parser_calls.append("parse")
            return ParsedDocument(
                source=SourceDocumentRef(
                    kb_id="risk_domain_knowledge",
                    doc_id="risk_guide",
                    version_id="risk_guide_v1",
                    file_path=str(tmp_path / "risk-guide.txt"),
                    doc_name="risk-guide.txt",
                    source_type=SourceType.TXT,
                ),
                parser_name="stub-parser",
                parser_version="stub-v1",
                raw_chunks=[
                    RawParsedChunk(
                        chunk_order=1,
                        raw_content="risk knowledge body",
                        chunk_type="paragraph",
                        title="title",
                        section_title="title",
                        section_path=["guide"],
                        page_start=1,
                        page_end=2,
                        position={"page": 1},
                        source_metadata={},
                    )
                ],
                document_metadata={"page_count": 2},
            )

    monkeypatch.setattr(settings, "risk_knowledge_indexing_max_page_count", 1, raising=False)

    _seed_version(tmp_path, source_type="txt", filename="risk-guide.txt")

    with AuthSessionLocal() as db:
        service = IndexingAdminService(
            db,
            parser_adapter=StubParser(),
            redis_client=fake_redis_client,
            job_launcher=lambda task: None,
        )
        launched = service.start_index("risk_guide_v1")

    with AuthSessionLocal() as db:
        service = IndexingAdminService(
            db,
            parser_adapter=StubParser(),
            redis_client=fake_redis_client,
            job_launcher=lambda task: None,
        )
        service.execute_job(launched.job_id)

    with AuthSessionLocal() as db:
        summary = IndexingAdminService(
            db,
            parser_adapter=StubParser(),
            redis_client=fake_redis_client,
            job_launcher=lambda task: None,
        ).get_job(launched.job_id)

        assert summary.status == "failed"
        assert "page" in (summary.error_message or "").lower()
        assert parser_calls == ["parse"]


def test_indexing_service_retry_failed_job_executes_successfully(auth_db, tmp_path, fake_redis_client, monkeypatch) -> None:
    from app.auth.database import AuthSessionLocal
    from app.core.config import settings
    from app.knowledge_base.schemas import SourceType
    from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService
    from app.risk_knowledge.ingestion.schemas import ParsedDocument, RawParsedChunk, SourceDocumentRef

    class DeterministicTestEmbeddingProvider:
        provider_name = "deterministic_test"
        max_batch_size = 16

        def embed(self, inputs):
            from app.risk_knowledge.embedding.schemas import EmbeddingVectorResult

            return [
                EmbeddingVectorResult(
                    chunk_id=item.chunk_id,
                    content_hash=item.content_hash,
                    provider=self.provider_name,
                    model="deterministic-v1",
                    dimension=2,
                    vector=[1.0, 2.0],
                    vector_checksum="sha256:vector",
                )
                for item in inputs
            ]

    class FailingParser:
        def parse(self, *_args, **_kwargs):
            raise ValueError("parser boom")

    class StubParser:
        def parse(self, ctx, *_args, **_kwargs):
            return ParsedDocument(
                source=SourceDocumentRef(
                    kb_id=ctx.kb_id,
                    doc_id=ctx.doc_id,
                    version_id=ctx.version_id,
                    file_path=ctx.file_path,
                    doc_name=ctx.doc_name,
                    source_type=SourceType.PDF,
                ),
                parser_name="stub-parser",
                parser_version="stub-v1",
                raw_chunks=[
                    RawParsedChunk(
                        chunk_order=1,
                        raw_content="risk retry body",
                        chunk_type="paragraph",
                        title="title",
                        section_title="title",
                        section_path=["guide"],
                        page_start=1,
                        page_end=1,
                        position={"page": 1},
                        source_metadata={},
                    )
                ],
                document_metadata={"page_count": 1},
            )

    monkeypatch.setattr(settings, "risk_knowledge_faiss_artifact_dir", str(tmp_path / "faiss"), raising=False)

    _seed_version(tmp_path, source_type="pdf", filename="retry.pdf")

    with AuthSessionLocal() as db:
        failing_service = IndexingAdminService(
            db,
            parser_adapter=FailingParser(),
            redis_client=fake_redis_client,
            embedding_provider=DeterministicTestEmbeddingProvider(),
            job_launcher=lambda task: None,
        )
        failed_launch = failing_service.start_index("risk_guide_v1")

    with AuthSessionLocal() as db:
        IndexingAdminService(
            db,
            parser_adapter=FailingParser(),
            redis_client=fake_redis_client,
            embedding_provider=DeterministicTestEmbeddingProvider(),
            job_launcher=lambda task: None,
        ).execute_job(failed_launch.job_id)

    with AuthSessionLocal() as db:
        retry_service = IndexingAdminService(
            db,
            parser_adapter=StubParser(),
            redis_client=fake_redis_client,
            embedding_provider=DeterministicTestEmbeddingProvider(),
            job_launcher=lambda task: None,
        )
        retry_launch = retry_service.retry_job(failed_launch.job_id)
        retry_service.execute_job(retry_launch.job_id)
        retry_summary = retry_service.get_job(retry_launch.job_id)

    assert retry_summary.status == "completed"
    assert retry_summary.retry_of_job_id == failed_launch.job_id
    assert retry_summary.active_manifest_index_id is not None


def test_indexing_service_rebuild_executes_and_creates_new_manifest(auth_db, tmp_path, fake_redis_client, monkeypatch) -> None:
    from app.auth.database import AuthSessionLocal
    from app.core.config import settings
    from app.knowledge_base.schemas import SourceType
    from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService
    from app.risk_knowledge.ingestion.schemas import ParsedDocument, RawParsedChunk, SourceDocumentRef

    class DeterministicTestEmbeddingProvider:
        provider_name = "deterministic_test"
        max_batch_size = 16

        def embed(self, inputs):
            from app.risk_knowledge.embedding.schemas import EmbeddingVectorResult

            return [
                EmbeddingVectorResult(
                    chunk_id=item.chunk_id,
                    content_hash=item.content_hash,
                    provider=self.provider_name,
                    model="deterministic-v1",
                    dimension=2,
                    vector=[1.0, 2.0],
                    vector_checksum="sha256:vector",
                )
                for item in inputs
            ]

    class StubParser:
        def parse(self, ctx, *_args, **_kwargs):
            return ParsedDocument(
                source=SourceDocumentRef(
                    kb_id=ctx.kb_id,
                    doc_id=ctx.doc_id,
                    version_id=ctx.version_id,
                    file_path=ctx.file_path,
                    doc_name=ctx.doc_name,
                    source_type=SourceType.PDF,
                ),
                parser_name="stub-parser",
                parser_version="stub-v1",
                raw_chunks=[
                    RawParsedChunk(
                        chunk_order=1,
                        raw_content="risk rebuild body",
                        chunk_type="paragraph",
                        title="title",
                        section_title="title",
                        section_path=["guide"],
                        page_start=1,
                        page_end=1,
                        position={"page": 1},
                        source_metadata={},
                    )
                ],
                document_metadata={"page_count": 1},
            )

    monkeypatch.setattr(settings, "risk_knowledge_faiss_artifact_dir", str(tmp_path / "faiss"), raising=False)

    _seed_version(tmp_path, source_type="pdf", filename="rebuild.pdf")

    with AuthSessionLocal() as db:
        service = IndexingAdminService(
            db,
            parser_adapter=StubParser(),
            redis_client=fake_redis_client,
            embedding_provider=DeterministicTestEmbeddingProvider(),
            job_launcher=lambda task: None,
        )
        first_launch = service.start_index("risk_guide_v1")
        service.execute_job(first_launch.job_id)
        first_summary = service.get_job(first_launch.job_id)
        rebuild_launch = service.start_rebuild("risk_guide_v1")
        service.execute_job(rebuild_launch.job_id)
        rebuild_summary = service.get_job(rebuild_launch.job_id)

    assert first_summary.status == "completed"
    assert rebuild_summary.status == "completed"
    assert rebuild_summary.active_manifest_index_id is not None
    assert rebuild_summary.active_manifest_index_id != first_summary.active_manifest_index_id


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
