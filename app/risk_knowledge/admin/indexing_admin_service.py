"""Admin-facing indexing job management for M2D-14A."""

from __future__ import annotations

from collections.abc import Callable
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
    SqlAlchemyKnowledgeIngestJobRepository,
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
from app.risk_knowledge.admin.schemas import (
    IndexingJobLaunchResponse,
    IndexingJobSummaryResponse,
    VersionActivateResponse,
)
from app.risk_knowledge.embedding.factory import build_embedding_provider_from_settings
from app.risk_knowledge.ingestion.context import IngestionContext
from app.risk_knowledge.ingestion.swxy_parser_adapter import SwxyParserAdapter
from app.risk_knowledge.persistence.repositories import SqlAlchemyFaissIndexRepository
from app.risk_knowledge.runtime.orchestrator import IndexingOrchestrator
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
        self._job_launcher(
            lambda: self._run_job(
                job_id=job.job_id,
                document_id=document.doc_id,
                version_id=version.version_id,
                trigger=trigger,
                failed_job_id=failed_job.job_id if failed_job is not None else None,
            )
        )
        return IndexingJobLaunchResponse(
            result="accepted",
            job_id=job.job_id,
            version_id=version.version_id,
            status=job.status.value,
            trigger=job.trigger.value,
            latest_manifest_index_id=version.latest_manifest_index_id,
            active_manifest_index_id=version.active_manifest_index_id,
        )

    def _run_job(
        self,
        *,
        job_id: str,
        document_id: str,
        version_id: str,
        trigger: IndexingJobTrigger,
        failed_job_id: str | None,
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
            try:
                job_service.transition_job(job_id, IndexingJobStatus.RUNNING, current_step=IngestStep.QUEUED)
                db.commit()
                parsed = self._parser_adapter.parse(
                    IngestionContext(
                        kb_id=document.kb_id,
                        doc_id=document.doc_id,
                        version_id=version.version_id,
                        job_id=job_id,
                        file_path=self._resolve_local_file(version.file_uri),
                        doc_name=document.doc_name,
                        source_type=document.source_type,
                    )
                )
                orchestrator = self._build_orchestrator()
                if trigger == IndexingJobTrigger.RETRY and failed_job_id is not None:
                    orchestrator.start_retry(
                        parsed_document=parsed,
                        document=document,
                        version=version,
                        failed_job_id=failed_job_id,
                        job_id=job_id,
                    )
                elif trigger == IndexingJobTrigger.REBUILD_FROM_PARSED:
                    orchestrator.start_rebuild_from_parsed(
                        parsed_document=parsed,
                        document=document,
                        version=version,
                        job_id=job_id,
                    )
                else:
                    orchestrator.start_initial_index(
                        parsed_document=parsed,
                        document=document,
                        version=version,
                        job_id=job_id,
                    )
            except Exception as exc:  # pylint: disable=broad-except
                try:
                    refreshed_version = doc_repo.get_version(version_id)
                    if refreshed_version is not None:
                        doc_repo.update_version(
                            refreshed_version.model_copy(update={"status": DocumentVersionStatus.FAILED})
                        )
                    if job_repo.get(job_id) is not None:
                        job_service.fail_job(job_id, str(exc))
                    db.commit()
                except Exception:
                    db.rollback()

    def _build_orchestrator(self) -> IndexingOrchestrator:
        redis_client = self._get_redis_client()
        embedding_provider = self._embedding_provider or build_embedding_provider_from_settings()
        if self._orchestrator_factory is not None:
            return self._orchestrator_factory(redis_client, embedding_provider)
        return IndexingOrchestrator(
            redis_client=redis_client,
            embedding_provider=embedding_provider,
            artifact_root=settings.resolve_path(settings.risk_knowledge_faiss_artifact_dir),
        )

    def _get_runtime_state(self, job_id: str):
        try:
            return self._build_runtime_state_store().get(job_id), True
        except Exception:
            return None, False

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
            latest_manifest_index_id=(
                runtime_state.latest_manifest_index_id if runtime_state is not None else job.latest_manifest_index_id
            ),
            active_manifest_index_id=(
                runtime_state.active_manifest_index_id if runtime_state is not None else job.active_manifest_index_id
            ),
            started_at=runtime_state.started_at if runtime_state is not None else job.started_at,
            completed_at=runtime_state.completed_at if runtime_state is not None else job.completed_at,
            last_heartbeat_at=(
                runtime_state.last_heartbeat_at if runtime_state is not None else job.last_heartbeat_at
            ),
            runtime_state_available=runtime_state_available and runtime_state is not None,
            runtime_status=runtime_state.runtime_status if runtime_state is not None else None,
            runtime_current_step=runtime_state.current_step if runtime_state is not None else None,
            progress_completed_steps=runtime_state.progress_completed_steps if runtime_state is not None else None,
            progress_total_steps=runtime_state.progress_total_steps if runtime_state is not None else None,
            progress_message=runtime_state.progress_message if runtime_state is not None else None,
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
            if job.status in {IndexingJobStatus.PENDING, IndexingJobStatus.RUNNING}:
                return job
        return None

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
