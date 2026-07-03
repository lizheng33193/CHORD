"""Admin-facing indexing job management for M2D-14A."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from threading import Thread

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.database import AuthSessionLocal
from app.core.config import settings
from app.knowledge_base.id_factory import build_indexing_job_id
from app.knowledge_base.models import KnowledgeIngestJobModel
from app.knowledge_base.repositories.sqlalchemy import (
    SqlAlchemyKnowledgeDocumentRepository,
    SqlAlchemyKnowledgeIngestArtifactRepository,
    SqlAlchemyKnowledgeIngestJobControlRepository,
    SqlAlchemyKnowledgeIngestJobRepository,
    SqlAlchemyKnowledgeIngestJobRuntimeStateRepository,
)
from app.knowledge_base.schemas import (
    DocumentVersionStatus,
    IndexingJobStatus,
    IndexingJobTrigger,
    IngestStep,
)
from app.knowledge_base.services.document_service import DocumentService
from app.knowledge_base.services.ingest_job_service import IngestJobService
from app.risk_knowledge.admin.errors import (
    IndexingJobMissingAdminError,
    InvalidActivationStateAdminError,
    InvalidAdminRequestError,
    KnowledgeDocumentMissingAdminError,
    KnowledgeDocumentVersionMissingAdminError,
    ManifestMissingAdminError,
    RetryNotAllowedAdminError,
    RunningIndexingJobConflictAdminError,
)
from app.risk_knowledge.admin.artifact_cleanup_service import ArtifactCleanupService
from app.risk_knowledge.admin.schemas import (
    ArtifactCleanupResponse,
    IndexingJobLaunchResponse,
    IndexingJobCancelResponse,
    IndexingJobSummaryResponse,
    VersionActivateResponse,
)
from app.risk_knowledge.embedding.factory import build_embedding_provider_from_settings
from app.risk_knowledge.ingestion.context import IngestionContext
from app.risk_knowledge.ingestion.schemas import ParsedDocument
from app.risk_knowledge.ingestion.swxy_parser_adapter import SwxyParserAdapter
from app.risk_knowledge.persistence.repositories import SqlAlchemyFaissIndexRepository
from app.risk_knowledge.runtime.orchestrator import IndexingOrchestrator
from app.risk_knowledge.runtime.progress import (
    DEFAULT_PROGRESS_TOTAL_STEPS,
    IndexingProgressUpdater,
    ProgressUpdate,
    resolve_stage_progress,
)
from app.risk_knowledge.runtime.errors import IndexingGuardrailError
from app.risk_knowledge.runtime.job_control import DurableJobControlService
from app.risk_knowledge.runtime.redis_state import RedisIndexingTaskStateStore

_JobLauncher = Callable[[Callable[[], None]], None]


def _default_job_launcher(task: Callable[[], None]) -> None:
    worker = Thread(target=task, daemon=True, name="risk-knowledge-admin-indexing")
    worker.start()


class IndexingAdminService:
    def __init__(
        self,
        db: Session,
        *,
        parser_adapter: SwxyParserAdapter | None = None,
        redis_client=None,
        embedding_provider=None,
        job_launcher: _JobLauncher | None = None,
        session_factory: sessionmaker | Callable[[], Session] = AuthSessionLocal,
        orchestrator_factory: Callable[[object, object], IndexingOrchestrator] | None = None,
    ) -> None:
        self._db = db
        self._doc_repo = SqlAlchemyKnowledgeDocumentRepository(db)
        self._job_repo = SqlAlchemyKnowledgeIngestJobRepository(db)
        self._control_repo = SqlAlchemyKnowledgeIngestJobControlRepository(db)
        self._artifact_repo = SqlAlchemyKnowledgeIngestArtifactRepository(db)
        self._runtime_state_repo = SqlAlchemyKnowledgeIngestJobRuntimeStateRepository(db)
        self._document_service = DocumentService(self._doc_repo)
        self._job_service = IngestJobService(self._job_repo)
        self._manifest_repo = SqlAlchemyFaissIndexRepository(db)
        self._parser_adapter = parser_adapter or SwxyParserAdapter()
        self._redis_client = redis_client
        self._embedding_provider = embedding_provider
        self._job_launcher = job_launcher or _default_job_launcher
        self._session_factory = session_factory
        self._orchestrator_factory = orchestrator_factory

    def start_index(self, version_id: str) -> IndexingJobLaunchResponse:
        document, version = self._load_document_and_version(version_id)
        existing_job = self._find_running_job(version.version_id)
        if existing_job is not None:
            return IndexingJobLaunchResponse(
                result="existing_job",
                job_id=existing_job.job_id,
                version_id=version.version_id,
                status=existing_job.status.value,
                trigger=existing_job.trigger.value,
                latest_manifest_index_id=existing_job.latest_manifest_index_id or version.latest_manifest_index_id,
                active_manifest_index_id=existing_job.active_manifest_index_id or version.active_manifest_index_id,
            )
        if self._has_valid_active_manifest(version):
            return IndexingJobLaunchResponse(
                result="already_indexed",
                job_id=version.last_job_id,
                version_id=version.version_id,
                status=version.status.value,
                trigger=None,
                latest_manifest_index_id=version.latest_manifest_index_id,
                active_manifest_index_id=version.active_manifest_index_id,
            )
        return self._enqueue_job(
            document_id=document.doc_id,
            version_id=version.version_id,
            trigger=IndexingJobTrigger.INITIAL_INDEX,
            failed_job_id=None,
        )

    def start_rebuild(self, version_id: str) -> IndexingJobLaunchResponse:
        document, version = self._load_document_and_version(version_id)
        existing_job = self._find_running_job(version.version_id)
        if existing_job is not None:
            raise RunningIndexingJobConflictAdminError(
                "indexing job already running for version",
                resource_id=existing_job.job_id,
                state=existing_job.status.value,
            )
        return self._enqueue_job(
            document_id=document.doc_id,
            version_id=version.version_id,
            trigger=IndexingJobTrigger.REBUILD_FROM_PARSED,
            failed_job_id=None,
        )

    def retry_job(self, job_id: str) -> IndexingJobLaunchResponse:
        failed_job = self._get_job(job_id)
        if failed_job.status != IndexingJobStatus.FAILED:
            raise RetryNotAllowedAdminError(
                "retry only supports failed durable jobs on the current baseline",
                resource_id=job_id,
                state=failed_job.status.value,
            )
        existing_job = self._find_running_job(failed_job.version_id)
        if existing_job is not None:
            raise RunningIndexingJobConflictAdminError(
                "indexing job already running for version",
                resource_id=existing_job.job_id,
                state=existing_job.status.value,
            )
        return self._enqueue_job(
            document_id=failed_job.doc_id,
            version_id=failed_job.version_id,
            trigger=IndexingJobTrigger.RETRY,
            failed_job_id=failed_job.job_id,
        )

    def activate_version(self, version_id: str, *, manifest_index_id: str | None = None) -> VersionActivateResponse:
        document, version = self._load_document_and_version(version_id)
        target_manifest_id = manifest_index_id or version.latest_manifest_index_id or version.active_manifest_index_id
        if not target_manifest_id:
            raise ManifestMissingAdminError(
                "manifest not found for version activation",
                resource_id=version_id,
            )

        target_manifest = self._manifest_repo.get(target_manifest_id)
        if target_manifest is None or target_manifest.version_id != version.version_id:
            raise ManifestMissingAdminError(
                "manifest not found for version activation",
                resource_id=target_manifest_id,
            )

        if (
            version.status == DocumentVersionStatus.ACTIVE
            and version.active_manifest_index_id == target_manifest.index_id
            and target_manifest.is_active
        ):
            return VersionActivateResponse(
                result="already_active",
                version_id=version.version_id,
                document_id=document.doc_id,
                manifest_index_id=target_manifest.index_id,
                status=version.status.value,
            )

        if version.status not in {DocumentVersionStatus.INDEXED, DocumentVersionStatus.ACTIVE}:
            raise InvalidActivationStateAdminError(
                "version must be indexed before activation",
                resource_id=version.version_id,
                state=version.status.value,
            )

        self._manifest_repo.activate_manifest(version_id=version.version_id, index_id=target_manifest.index_id)
        updated_version = self._doc_repo.update_version(
            version.model_copy(
                update={
                    "status": DocumentVersionStatus.ACTIVE if version.status == DocumentVersionStatus.ACTIVE else DocumentVersionStatus.INDEXED,
                    "latest_manifest_index_id": target_manifest.index_id,
                    "active_manifest_index_id": target_manifest.index_id,
                }
            )
        )
        activated = self._document_service.activate_version(updated_version.version_id)
        self._db.commit()
        return VersionActivateResponse(
            result="activated",
            version_id=activated.version_id,
            document_id=document.doc_id,
            manifest_index_id=target_manifest.index_id,
            status=activated.status.value,
        )

    def get_job(self, job_id: str) -> IndexingJobSummaryResponse:
        return self._build_job_summary(self._get_job(job_id))

    def list_jobs(
        self,
        *,
        kb_id: str | None = None,
        document_id: str | None = None,
        version_id: str | None = None,
        status: str | None = None,
    ) -> list[IndexingJobSummaryResponse]:
        statement = select(KnowledgeIngestJobModel).order_by(
            KnowledgeIngestJobModel.created_at.desc(),
            KnowledgeIngestJobModel.job_id.desc(),
        )
        if kb_id:
            statement = statement.where(KnowledgeIngestJobModel.kb_id == kb_id)
        if document_id:
            statement = statement.where(KnowledgeIngestJobModel.doc_id == document_id)
        if version_id:
            statement = statement.where(KnowledgeIngestJobModel.version_id == version_id)
        if status:
            statement = statement.where(KnowledgeIngestJobModel.status == status)
        models = list(self._db.scalars(statement).all())
        items = []
        for model in models:
            job = self._job_repo.get(model.job_id)
            if job is not None:
                items.append(self._build_job_summary(job))
        return items

    def _enqueue_job(
        self,
        *,
        document_id: str,
        version_id: str,
        trigger: IndexingJobTrigger,
        failed_job_id: str | None,
    ) -> IndexingJobLaunchResponse:
        document = self._require_document(document_id)
        version = self._require_version(version_id)
        failed_job = self._get_job(failed_job_id) if failed_job_id else None
        attempt = 1 if failed_job is None else failed_job.attempt + 1
        job_id = build_indexing_job_id()
        job = self._job_service.create_job(
            kb_id=document.kb_id,
            doc_id=document.doc_id,
            version_id=version.version_id,
            job_id=job_id,
            trigger=trigger,
            attempt=attempt,
            max_attempts=settings.risk_knowledge_indexing_max_retries,
            root_job_id=failed_job.root_job_id if failed_job is not None else job_id,
            retry_of_job_id=failed_job.job_id if failed_job is not None else None,
        )
        self._db.commit()
        return IndexingJobLaunchResponse(
            result="accepted",
            job_id=job.job_id,
            version_id=version.version_id,
            status=job.status.value,
            trigger=job.trigger.value,
            latest_manifest_index_id=version.latest_manifest_index_id,
            active_manifest_index_id=version.active_manifest_index_id,
        )

    def cancel_job(self, job_id: str) -> IndexingJobCancelResponse:
        job = self._get_job(job_id)
        now = self._now()
        if job.status in {IndexingJobStatus.QUEUED, IndexingJobStatus.PENDING}:
            updated = self._job_service.transition_job(job_id, IndexingJobStatus.CANCELED, current_step=IngestStep.CANCELED)
            self._control_repo.upsert(
                self._control_repo.get(job_id) or self._build_empty_control(job_id)
            )
            self._db.commit()
            return IndexingJobCancelResponse(result="canceled", job_id=updated.job_id, status=updated.status.value)
        if job.status == IndexingJobStatus.RUNNING:
            current = self._control_repo.get(job_id) or self._build_empty_control(job_id)
            self._control_repo.upsert(current.model_copy(update={"cancel_requested_at": now}))
            self._db.commit()
            return IndexingJobCancelResponse(result="cancel_requested", job_id=job.job_id, status=job.status.value)
        raise InvalidAdminRequestError(
            "only queued or running jobs can be canceled",
            resource_id=job_id,
            state=job.status.value,
        )

    def cleanup_artifacts(self, *, dry_run: bool = True, root: str | None = None) -> ArtifactCleanupResponse:
        return ArtifactCleanupService(self._db).cleanup(dry_run=dry_run, root=root)

    def execute_job(self, job_id: str, *, lease_owner: str | None = None) -> None:
        job = self._get_job(job_id)
        control_state = self._control_repo.get(job_id)
        if control_state is not None and control_state.cancel_requested_at is not None and job.status in {
            IndexingJobStatus.QUEUED,
            IndexingJobStatus.PENDING,
        }:
            self._job_service.transition_job(job_id, IndexingJobStatus.CANCELED, current_step=IngestStep.CANCELED)
            self._db.commit()
            return
        try:
            self._run_job(
                job_id=job.job_id,
                document_id=job.doc_id,
                version_id=job.version_id,
                trigger=job.trigger,
                failed_job_id=job.retry_of_job_id,
                lease_owner=lease_owner,
            )
        finally:
            if lease_owner is not None:
                try:
                    with self._session_factory() as db:
                        DurableJobControlService(
                            db,
                            lease_seconds=settings.risk_knowledge_indexing_stale_after_seconds,
                        ).release_job(job.job_id, owner=lease_owner)
                except Exception:
                    pass

    def _run_job(
        self,
        *,
        job_id: str,
        document_id: str,
        version_id: str,
        trigger: IndexingJobTrigger,
        failed_job_id: str | None,
        lease_owner: str | None = None,
    ) -> None:
        with self._session_factory() as db:
            doc_repo = SqlAlchemyKnowledgeDocumentRepository(db)
            job_repo = SqlAlchemyKnowledgeIngestJobRepository(db)
            document_service = DocumentService(doc_repo)
            job_service = IngestJobService(job_repo)
            document = doc_repo.get_document(document_id)
            version = doc_repo.get_version(version_id)
            if document is None or version is None:
                if job_repo.get(job_id) is not None:
                    job_service.fail_job(job_id, "document or version not found before background execution")
                    db.commit()
                return
            file_path = self._resolve_local_file(version.file_uri)
            progress_updater: IndexingProgressUpdater | None = None
            current_step_ref = {"value": IngestStep.QUEUED}
            try:
                job = job_service.transition_job(job_id, IndexingJobStatus.RUNNING, current_step=IngestStep.QUEUED)
                db.commit()
                progress_updater = self._build_progress_updater(
                    job=job,
                    document=document,
                    version=version,
                    lease_owner=lease_owner,
                )
                current_step_ref["value"] = (
                    IngestStep.PARSING_PDF if document.source_type.value == "pdf" else IngestStep.PARSING_DOCUMENT
                )
                parse_started_at = self._now()
                file_size_bytes = self._resolve_file_size_bytes(file_path)
                self._assert_file_size_guard(file_size_bytes, current_step_ref["value"])
                progress_updater.update(
                    ProgressUpdate(
                        runtime_status="running",
                        current_step=current_step_ref["value"].value,
                        progress_message="parsing document",
                        progress_completed_steps=resolve_stage_progress(current_step_ref["value"].value),
                        progress_total_steps=DEFAULT_PROGRESS_TOTAL_STEPS,
                        file_size_bytes=file_size_bytes,
                    ),
                    force=True,
                )
                parsed = self._parser_adapter.parse(
                    IngestionContext(
                        kb_id=document.kb_id,
                        doc_id=document.doc_id,
                        version_id=version.version_id,
                        job_id=job_id,
                        file_path=file_path,
                        doc_name=document.doc_name,
                        source_type=document.source_type,
                    ),
                    progress_callback=self._build_parser_progress_callback(
                        document_source_type=document.source_type.value,
                        progress_updater=progress_updater,
                        current_step_ref=current_step_ref,
                    ),
                )
                page_count = self._estimate_page_count(parsed)
                current_step_ref["value"] = IngestStep.CHUNKING
                self._assert_page_count_guard(page_count, current_step_ref["value"])
                progress_updater.update(
                    ProgressUpdate(
                        runtime_status="running",
                        current_step=current_step_ref["value"].value,
                        progress_message="parser completed; building chunks",
                        progress_completed_steps=resolve_stage_progress(current_step_ref["value"].value),
                        progress_total_steps=DEFAULT_PROGRESS_TOTAL_STEPS,
                        file_size_bytes=file_size_bytes,
                        page_count=page_count,
                        parser_duration_ms=self._elapsed_ms(parse_started_at),
                    ),
                    force=True,
                )
                orchestrator = self._build_orchestrator()
                if trigger == IndexingJobTrigger.RETRY and failed_job_id is not None:
                    orchestrator.start_retry(
                        parsed_document=parsed,
                        document=document,
                        version=version,
                        failed_job_id=failed_job_id,
                        job_id=job_id,
                        progress_updater=progress_updater,
                    )
                elif trigger == IndexingJobTrigger.REBUILD_FROM_PARSED:
                    orchestrator.start_rebuild_from_parsed(
                        parsed_document=parsed,
                        document=document,
                        version=version,
                        job_id=job_id,
                        progress_updater=progress_updater,
                    )
                else:
                    orchestrator.start_initial_index(
                        parsed_document=parsed,
                        document=document,
                        version=version,
                        job_id=job_id,
                        progress_updater=progress_updater,
                    )
            except Exception as exc:  # pylint: disable=broad-except
                try:
                    if job_repo.get(job_id) is not None:
                        job_service.fail_job(job_id, str(exc), current_step=current_step_ref["value"])
                    db.commit()
                except Exception:
                    db.rollback()

                try:
                    refreshed_version = doc_repo.get_version(version_id)
                    if refreshed_version is not None and refreshed_version.status != DocumentVersionStatus.FAILED:
                        doc_repo.update_version(
                            refreshed_version.model_copy(update={"status": DocumentVersionStatus.FAILED})
                        )
                    db.commit()
                except Exception:
                    db.rollback()

                if progress_updater is not None:
                    try:
                        progress_updater.update(
                            ProgressUpdate(
                                runtime_status="failed",
                                current_step=current_step_ref["value"].value,
                                progress_message=f"failed during {current_step_ref['value'].value}: {exc}",
                                progress_completed_steps=resolve_stage_progress(current_step_ref["value"].value),
                                progress_total_steps=DEFAULT_PROGRESS_TOTAL_STEPS,
                                error_code=exc.__class__.__name__,
                                error_message=str(exc),
                                total_duration_ms=self._elapsed_ms(job.started_at if 'job' in locals() else None),
                                completed=True,
                            ),
                            force=True,
                        )
                    except Exception:
                        pass

    def _build_orchestrator(self) -> IndexingOrchestrator:
        redis_client = self._get_redis_client()
        embedding_provider = self._embedding_provider or build_embedding_provider_from_settings()
        if self._orchestrator_factory is not None:
            return self._orchestrator_factory(redis_client, embedding_provider)
        return IndexingOrchestrator(
            redis_client=redis_client,
            embedding_provider=embedding_provider,
            artifact_root=settings.resolve_path(settings.risk_knowledge_faiss_artifact_dir),
            session_factory=self._session_factory,
        )

    def _get_runtime_state(self, job_id: str):
        try:
            return self._build_runtime_state_store().get(job_id), True
        except Exception:
            return None, False

    def _get_durable_runtime_state(self, job_id: str):
        try:
            return self._runtime_state_repo.get(job_id)
        except Exception:
            return None

    def _build_runtime_state_store(self) -> RedisIndexingTaskStateStore:
        return RedisIndexingTaskStateStore(
            client=self._get_redis_client(),
            key_prefix=settings.risk_knowledge_redis_key_prefix,
            state_ttl_seconds=settings.risk_knowledge_indexing_state_ttl_seconds,
        )

    def _get_redis_client(self):
        if self._redis_client is not None:
            return self._redis_client
        import redis

        self._redis_client = redis.from_url(settings.risk_knowledge_redis_url, decode_responses=True)
        return self._redis_client

    def _build_job_summary(self, job) -> IndexingJobSummaryResponse:
        runtime_state, runtime_state_available = self._get_runtime_state(job.job_id)
        durable_runtime_state = self._get_durable_runtime_state(job.job_id)
        control_state = self._control_repo.get(job.job_id)
        artifacts = self._artifact_repo.list_by_job(job.job_id)
        progress_state = runtime_state or durable_runtime_state
        started_at = self._first_non_none(
            runtime_state.started_at if runtime_state is not None else None,
            job.started_at,
        )
        completed_at = self._first_non_none(
            runtime_state.completed_at if runtime_state is not None else None,
            job.completed_at,
        )
        last_heartbeat_at = self._first_non_none(
            runtime_state.last_heartbeat_at if runtime_state is not None else None,
            job.last_heartbeat_at,
        )
        total_duration_ms = self._first_non_none(
            progress_state.total_duration_ms if progress_state is not None else None,
            self._elapsed_ms(started_at, completed_at or last_heartbeat_at),
        )
        return IndexingJobSummaryResponse(
            job_id=job.job_id,
            kb_id=job.kb_id,
            document_id=job.doc_id,
            version_id=job.version_id,
            trigger=job.trigger.value,
            status=job.status.value,
            current_step=job.current_step.value,
            error_message=job.error_message,
            attempt=job.attempt,
            max_attempts=job.max_attempts,
            root_job_id=job.root_job_id,
            retry_of_job_id=job.retry_of_job_id,
            latest_manifest_index_id=self._first_non_none(
                runtime_state.latest_manifest_index_id if runtime_state is not None else None,
                job.latest_manifest_index_id,
            ),
            active_manifest_index_id=self._first_non_none(
                runtime_state.active_manifest_index_id if runtime_state is not None else None,
                job.active_manifest_index_id,
            ),
            started_at=started_at,
            completed_at=completed_at,
            last_heartbeat_at=last_heartbeat_at,
            lease_owner=control_state.lease_owner if control_state is not None else None,
            lease_expires_at=control_state.lease_expires_at if control_state is not None else None,
            cancel_requested_at=control_state.cancel_requested_at if control_state is not None else None,
            stale_detected_at=control_state.stale_detected_at if control_state is not None else None,
            stale_reason=control_state.stale_reason if control_state is not None else None,
            artifact_count=len(artifacts),
            runtime_state_available=runtime_state_available and runtime_state is not None,
            runtime_status=runtime_state.runtime_status if runtime_state is not None else None,
            runtime_current_step=runtime_state.current_step if runtime_state is not None else None,
            progress_completed_steps=self._coalesce_progress_field(
                runtime_state,
                durable_runtime_state,
                "progress_completed_steps",
            ),
            progress_total_steps=self._coalesce_progress_field(
                runtime_state,
                durable_runtime_state,
                "progress_total_steps",
            ),
            progress_message=self._coalesce_progress_field(runtime_state, durable_runtime_state, "progress_message"),
            elapsed_seconds=self._elapsed_seconds(total_duration_ms),
            file_size_bytes=self._coalesce_progress_field(runtime_state, durable_runtime_state, "file_size_bytes"),
            page_count=self._coalesce_progress_field(runtime_state, durable_runtime_state, "page_count"),
            chunk_count=self._coalesce_progress_field(runtime_state, durable_runtime_state, "chunk_count"),
            embedding_count=self._coalesce_progress_field(runtime_state, durable_runtime_state, "embedding_count"),
            embedding_batch_count=self._coalesce_progress_field(runtime_state, durable_runtime_state, "embedding_batch_count"),
            embedding_batches_completed=self._coalesce_progress_field(runtime_state, durable_runtime_state, "embedding_batches_completed"),
            vector_mapping_count=self._coalesce_progress_field(runtime_state, durable_runtime_state, "vector_mapping_count"),
            parser_duration_ms=self._coalesce_progress_field(runtime_state, durable_runtime_state, "parser_duration_ms"),
            embedding_duration_ms=self._coalesce_progress_field(runtime_state, durable_runtime_state, "embedding_duration_ms"),
            faiss_duration_ms=self._coalesce_progress_field(runtime_state, durable_runtime_state, "faiss_duration_ms"),
            total_duration_ms=total_duration_ms,
        )

    def _load_document_and_version(self, version_id: str):
        version = self._require_version(version_id)
        document = self._require_document(version.doc_id)
        return document, version

    def _require_document(self, document_id: str):
        document = self._doc_repo.get_document(document_id)
        if document is None:
            raise KnowledgeDocumentMissingAdminError(
                "knowledge document not found",
                resource_id=document_id,
            )
        return document

    def _require_version(self, version_id: str):
        version = self._doc_repo.get_version(version_id)
        if version is None:
            raise KnowledgeDocumentVersionMissingAdminError(
                "knowledge document version not found",
                resource_id=version_id,
            )
        return version

    def _get_job(self, job_id: str):
        if job_id is None:
            raise IndexingJobMissingAdminError("indexing job not found")
        job = self._job_repo.get(job_id)
        if job is None:
            raise IndexingJobMissingAdminError(
                "indexing job not found",
                resource_id=job_id,
            )
        return job

    def _find_running_job(self, version_id: str):
        jobs = self._job_repo.list_by_version(version_id)
        for job in jobs:
            if job.status in {IndexingJobStatus.QUEUED, IndexingJobStatus.PENDING, IndexingJobStatus.RUNNING}:
                return job
        return None

    @staticmethod
    def _build_empty_control(job_id: str):
        from app.knowledge_base.schemas import KnowledgeIngestJobControl

        return KnowledgeIngestJobControl(job_id=job_id)

    def _has_valid_active_manifest(self, version) -> bool:
        if version.status not in {DocumentVersionStatus.INDEXED, DocumentVersionStatus.ACTIVE}:
            return False
        if not version.active_manifest_index_id:
            return False
        manifest = self._manifest_repo.get(version.active_manifest_index_id)
        return manifest is not None and manifest.version_id == version.version_id and manifest.is_active

    @staticmethod
    def _resolve_local_file(file_uri: str) -> str:
        path = Path(file_uri)
        if not path.exists():
            raise InvalidAdminRequestError(
                "indexed file is missing on local storage",
                resource_id=file_uri,
            )
        return str(path)

    def _build_progress_updater(self, *, job, document, version, lease_owner: str | None = None) -> IndexingProgressUpdater:
        heartbeat_callback = None
        if lease_owner is not None:
            def _heartbeat() -> None:
                with self._session_factory() as db:
                    DurableJobControlService(
                        db,
                        lease_seconds=settings.risk_knowledge_indexing_stale_after_seconds,
                    ).heartbeat(job.job_id, owner=lease_owner)

            heartbeat_callback = _heartbeat
        return IndexingProgressUpdater(
            job=job,
            document=document,
            version=version,
            redis_state_store=self._build_runtime_state_store(),
            session_factory=self._session_factory,
            heartbeat_callback=heartbeat_callback,
        )

    def _build_parser_progress_callback(
        self,
        *,
        document_source_type: str,
        progress_updater: IndexingProgressUpdater,
        current_step_ref: dict[str, IngestStep],
    ) -> Callable[[float | None, str], None]:
        last_step: dict[str, IngestStep | None] = {"value": None}

        def _callback(_progress: float | None, message: str) -> None:
            step = self._map_parser_step(document_source_type, message)
            force = step != last_step["value"]
            last_step["value"] = step
            current_step_ref["value"] = step
            progress_updater.update(
                ProgressUpdate(
                    runtime_status="running",
                    current_step=step.value,
                    progress_message=message,
                    progress_completed_steps=resolve_stage_progress(step.value),
                    progress_total_steps=DEFAULT_PROGRESS_TOTAL_STEPS,
                ),
                force=force,
            )

        return _callback

    @staticmethod
    def _map_parser_step(document_source_type: str, message: str) -> IngestStep:
        normalized = message.strip().lower()
        if document_source_type == "pdf":
            if "ocr" in normalized:
                return IngestStep.OCR_RUNNING
            if "layout" in normalized:
                return IngestStep.LAYOUT_ANALYZING
            if "table" in normalized:
                return IngestStep.TABLE_ANALYZING
            if "merged" in normalized or "merge" in normalized:
                return IngestStep.TEXT_MERGING
            return IngestStep.PARSING_PDF
        return IngestStep.PARSING_DOCUMENT

    @staticmethod
    def _estimate_page_count(parsed_document: ParsedDocument) -> int | None:
        page_numbers = [
            max(filter(None, [chunk.page_start, chunk.page_end]))
            for chunk in parsed_document.raw_chunks
            if chunk.page_start is not None or chunk.page_end is not None
        ]
        if not page_numbers:
            return None
        return max(page_numbers)

    @staticmethod
    def _resolve_file_size_bytes(file_path: str) -> int | None:
        try:
            return Path(file_path).stat().st_size
        except OSError:
            return None

    @staticmethod
    def _assert_file_size_guard(file_size_bytes: int | None, current_step: IngestStep) -> None:
        if file_size_bytes is None:
            return
        if file_size_bytes <= settings.risk_knowledge_indexing_max_file_size_bytes:
            return
        raise IndexingGuardrailError(
            f"file_size guard exceeded during {current_step.value}: "
            f"{file_size_bytes} > {settings.risk_knowledge_indexing_max_file_size_bytes}"
        )

    @staticmethod
    def _assert_page_count_guard(page_count: int | None, current_step: IngestStep) -> None:
        if page_count is None:
            return
        if page_count <= settings.risk_knowledge_indexing_max_page_count:
            return
        raise IndexingGuardrailError(
            f"page_count guard exceeded during {current_step.value}: "
            f"{page_count} > {settings.risk_knowledge_indexing_max_page_count}"
        )

    @staticmethod
    def _first_non_none(*values):
        for value in values:
            if value is not None:
                return value
        return None

    @classmethod
    def _coalesce_progress_field(cls, runtime_state, durable_runtime_state, field_name: str):
        return cls._first_non_none(
            getattr(runtime_state, field_name, None) if runtime_state is not None else None,
            getattr(durable_runtime_state, field_name, None) if durable_runtime_state is not None else None,
        )

    @staticmethod
    def _elapsed_ms(started_at: datetime | None, ended_at: datetime | None = None) -> int | None:
        if started_at is None:
            return None
        end = ended_at or datetime.now(UTC).replace(tzinfo=None)
        return max(0, int((end - started_at).total_seconds() * 1000))

    @staticmethod
    def _elapsed_seconds(total_duration_ms: int | None) -> int | None:
        if total_duration_ms is None:
            return None
        return total_duration_ms // 1000

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)
