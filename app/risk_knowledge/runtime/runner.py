"""In-process indexing job runner for M2D-9."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from app.auth.database import AuthSessionLocal
from app.core.config import settings
from app.knowledge_base.id_factory import build_faiss_index_id, build_indexing_job_id
from app.knowledge_base.repositories.sqlalchemy import (
    SqlAlchemyKnowledgeDocumentRepository,
    SqlAlchemyKnowledgeIngestJobRepository,
)
from app.knowledge_base.schemas import (
    DocumentVersionStatus,
    IndexingJobStatus,
    IndexingJobStep,
    IndexingJobTrigger,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    KnowledgeIngestJob,
)
from app.knowledge_base.services.document_service import DocumentService
from app.risk_knowledge.embedding.batch_service import EmbeddingBatchService
from app.risk_knowledge.indexing.faiss_store import FaissIndexStore, build_faiss_fingerprint
from app.risk_knowledge.indexing.schemas import FaissIndexManifestDraft
from app.risk_knowledge.ingestion.schemas import ParsedDocument
from app.risk_knowledge.metadata.chunk_builder import KnowledgeChunkBuilder
from app.risk_knowledge.persistence.repositories import (
    SqlAlchemyFaissIndexRepository,
    SqlAlchemyKnowledgeChunkEmbeddingRepository,
    SqlAlchemyKnowledgeChunkRepository,
)
from app.risk_knowledge.persistence.service import KnowledgeChunkPersistenceService
from app.risk_knowledge.runtime.errors import IndexingJobNotRetryableError
from app.risk_knowledge.runtime.progress import (
    DEFAULT_PROGRESS_TOTAL_STEPS,
    IndexingProgressUpdater,
    ProgressUpdate,
    resolve_stage_progress,
)
from app.risk_knowledge.runtime.redis_lock import RedisVersionLock
from app.risk_knowledge.runtime.redis_state import RedisIndexingTaskStateStore
from app.risk_knowledge.runtime.schemas import IndexingJobRunResult


@dataclass(frozen=True)
class RunnerDependencies:
    redis_state_store: RedisIndexingTaskStateStore
    version_lock: RedisVersionLock
    embedding_provider: object
    artifact_root: Path
    session_factory: Callable[[], Session] = AuthSessionLocal


class IndexingJobRunner:
    def __init__(
        self,
        *,
        dependencies: RunnerDependencies,
        lose_lock_before_activation: bool = False,
    ) -> None:
        self._deps = dependencies
        self._chunk_builder = KnowledgeChunkBuilder()
        self._lose_lock_before_activation = lose_lock_before_activation

    def run_initial_index(
        self,
        *,
        parsed_document: ParsedDocument,
        document: KnowledgeDocument,
        version: KnowledgeDocumentVersion,
        job_id: str | None = None,
        progress_updater: IndexingProgressUpdater | None = None,
    ) -> IndexingJobRunResult:
        return self._run(
            parsed_document=parsed_document,
            document=document,
            version=version,
            trigger=IndexingJobTrigger.INITIAL_INDEX,
            reuse_persisted_chunks=False,
            force_rebuild=False,
            failed_job=None,
            job_id=job_id,
            progress_updater=progress_updater,
        )

    def run_retry(
        self,
        *,
        parsed_document: ParsedDocument,
        document: KnowledgeDocument,
        version: KnowledgeDocumentVersion,
        failed_job: KnowledgeIngestJob,
        job_id: str | None = None,
        progress_updater: IndexingProgressUpdater | None = None,
    ) -> IndexingJobRunResult:
        if failed_job.status != IndexingJobStatus.FAILED:
            raise IndexingJobNotRetryableError(f"job is not retryable: {failed_job.job_id}")
        return self._run(
            parsed_document=parsed_document,
            document=document,
            version=version,
            trigger=IndexingJobTrigger.RETRY,
            reuse_persisted_chunks=False,
            force_rebuild=False,
            failed_job=failed_job,
            job_id=job_id,
            progress_updater=progress_updater,
        )

    def run_rebuild_from_parsed(
        self,
        *,
        parsed_document: ParsedDocument,
        document: KnowledgeDocument,
        version: KnowledgeDocumentVersion,
        job_id: str | None = None,
        progress_updater: IndexingProgressUpdater | None = None,
    ) -> IndexingJobRunResult:
        return self._run(
            parsed_document=parsed_document,
            document=document,
            version=version,
            trigger=IndexingJobTrigger.REBUILD_FROM_PARSED,
            reuse_persisted_chunks=False,
            force_rebuild=False,
            failed_job=None,
            job_id=job_id,
            progress_updater=progress_updater,
        )

    def run_rebuild_from_persisted_chunks(
        self,
        *,
        document: KnowledgeDocument,
        version: KnowledgeDocumentVersion,
        force: bool = False,
        job_id: str | None = None,
        progress_updater: IndexingProgressUpdater | None = None,
    ) -> IndexingJobRunResult:
        return self._run(
            parsed_document=None,
            document=document,
            version=version,
            trigger=IndexingJobTrigger.REBUILD_FROM_PERSISTED_CHUNKS,
            reuse_persisted_chunks=True,
            force_rebuild=force,
            failed_job=None,
            job_id=job_id,
            progress_updater=progress_updater,
        )

    def _run(
        self,
        *,
        parsed_document: ParsedDocument | None,
        document: KnowledgeDocument,
        version: KnowledgeDocumentVersion,
        trigger: IndexingJobTrigger,
        reuse_persisted_chunks: bool,
        force_rebuild: bool,
        failed_job: KnowledgeIngestJob | None,
        job_id: str | None,
        progress_updater: IndexingProgressUpdater | None,
    ) -> IndexingJobRunResult:
        self._validate_version_status(version, trigger)
        attempt = 1 if failed_job is None else failed_job.attempt + 1
        root_job_id = failed_job.root_job_id if failed_job is not None and failed_job.root_job_id else None
        job_id = job_id or build_indexing_job_id()
        job = self._create_job(
            job_id=job_id,
            document=document,
            version=version,
            trigger=trigger,
            attempt=attempt,
            root_job_id=root_job_id or job_id,
            retry_of_job_id=failed_job.job_id if failed_job is not None else None,
        )
        progress_updater = progress_updater or self._build_progress_updater(
            job=job,
            document=document,
            version=version,
        )
        started_at = job.started_at or self._now()
        lock_token: str | None = None
        current_step = IndexingJobStep.QUEUED
        chunk_count = 0
        embedding_count = 0
        embedding_batch_count = 0
        vector_mapping_count = 0
        embedding_duration_ms: int | None = None
        faiss_duration_ms: int | None = None

        try:
            lock_token = self._deps.version_lock.acquire(version.version_id)
            current_step = IndexingJobStep.LOCK_ACQUIRED
            progress_updater.update(
                ProgressUpdate(
                    runtime_status="running",
                    current_step=current_step.value,
                    progress_message="lock acquired",
                    progress_completed_steps=resolve_stage_progress(current_step.value),
                    progress_total_steps=DEFAULT_PROGRESS_TOTAL_STEPS,
                    lock_token=lock_token,
                    file_size_bytes=self._resolve_file_size_bytes(version.file_uri),
                ),
                force=True,
            )
            self._transition_version_running(version.version_id, trigger, job_id)
            self._deps.version_lock.renew(version.version_id, lock_token)

            if reuse_persisted_chunks:
                chunk_ids = self._list_chunk_ids(version.version_id)
                chunk_count = len(chunk_ids)
                current_step = IndexingJobStep.PERSISTING_CHUNKS
                progress_updater.update(
                    ProgressUpdate(
                        runtime_status="running",
                        current_step=current_step.value,
                        progress_message="reusing persisted chunks",
                        progress_completed_steps=resolve_stage_progress(current_step.value),
                        progress_total_steps=DEFAULT_PROGRESS_TOTAL_STEPS,
                        lock_token=lock_token,
                        chunk_count=chunk_count,
                    ),
                    force=True,
                )
            else:
                if parsed_document is None:
                    raise ValueError("parsed_document is required for parsed-document indexing flows")
                current_step = IndexingJobStep.CHUNKING
                progress_updater.update(
                    ProgressUpdate(
                        runtime_status="running",
                        current_step=current_step.value,
                        progress_message="building chunks",
                        progress_completed_steps=resolve_stage_progress(current_step.value),
                        progress_total_steps=DEFAULT_PROGRESS_TOTAL_STEPS,
                        lock_token=lock_token,
                    ),
                    force=True,
                )
                chunks = self._chunk_builder.build(parsed_document, document, version).chunks
                chunk_count = len(chunks)
                self._deps.version_lock.renew(version.version_id, lock_token)
                current_step = IndexingJobStep.PERSISTING_CHUNKS
                progress_updater.update(
                    ProgressUpdate(
                        runtime_status="running",
                        current_step=current_step.value,
                        progress_message="persisting chunks",
                        progress_completed_steps=resolve_stage_progress(current_step.value),
                        progress_total_steps=DEFAULT_PROGRESS_TOTAL_STEPS,
                        lock_token=lock_token,
                        chunk_count=chunk_count,
                    ),
                    force=True,
                )
                with self._deps.session_factory() as db:
                    KnowledgeChunkPersistenceService(db).persist_chunks(version, chunks)
                chunk_ids = [chunk.chunk_id for chunk in chunks]

            self._deps.version_lock.renew(version.version_id, lock_token)
            current_step = IndexingJobStep.EMBEDDING
            progress_updater.update(
                ProgressUpdate(
                    runtime_status="running",
                    current_step=current_step.value,
                    progress_message="embedding persisted chunks",
                    progress_completed_steps=resolve_stage_progress(current_step.value),
                    progress_total_steps=DEFAULT_PROGRESS_TOTAL_STEPS,
                    lock_token=lock_token,
                    chunk_count=chunk_count,
                ),
                force=True,
            )
            embedding_started_at = self._now()
            with self._deps.session_factory() as db:
                embedding_service = EmbeddingBatchService(
                    provider=self._deps.embedding_provider,
                    expected_dimension=version.embedding_dim or settings.risk_knowledge_embedding_dimension,
                    db=db,
                )
                embedding_service.embed_persisted_chunks(
                    version_id=version.version_id,
                    chunk_ids=chunk_ids,
                    progress_callback=self._build_embedding_progress_callback(
                        progress_updater=progress_updater,
                        lock_token=lock_token,
                        chunk_count=chunk_count,
                    ),
                )
                embedding_repo = SqlAlchemyKnowledgeChunkEmbeddingRepository(db)
                chunk_repo = SqlAlchemyKnowledgeChunkRepository(db)
                persisted_embeddings = embedding_repo.list_by_version(version.version_id)
                persisted_chunks = chunk_repo.list_by_version(version.version_id)

            chunk_count = len(persisted_chunks)
            embedding_count = len(persisted_embeddings)
            embedding_batch_count = self._embedding_batch_count(embedding_count)
            embedding_duration_ms = self._elapsed_ms(embedding_started_at)
            progress_updater.update(
                ProgressUpdate(
                    runtime_status="running",
                    current_step=IndexingJobStep.EMBEDDING.value,
                    progress_message="embedding completed",
                    progress_completed_steps=resolve_stage_progress(IndexingJobStep.EMBEDDING.value),
                    progress_total_steps=DEFAULT_PROGRESS_TOTAL_STEPS,
                    lock_token=lock_token,
                    chunk_count=chunk_count,
                    embedding_count=embedding_count,
                    embedding_batch_count=embedding_batch_count,
                    embedding_batches_completed=embedding_batch_count,
                    embedding_duration_ms=embedding_duration_ms,
                ),
                force=True,
            )

            actual_pairs = [(item.chunk_id, item.content_hash) for item in persisted_embeddings]
            fingerprint = build_faiss_fingerprint(
                kb_id=version.kb_id,
                version_id=version.version_id,
                provider=persisted_embeddings[0].provider,
                model=persisted_embeddings[0].model,
                dimension=persisted_embeddings[0].dimension,
                chunk_content_pairs=actual_pairs,
            )

            with self._deps.session_factory() as db:
                manifest_repo = SqlAlchemyFaissIndexRepository(db)
                existing_manifest = manifest_repo.get_active_by_version(version.version_id)
                if (
                    not force_rebuild
                    and existing_manifest is not None
                    and existing_manifest.build_fingerprint == fingerprint
                    and existing_manifest.checksum
                ):
                    active_index_id = existing_manifest.index_id
                    vector_mapping_count = existing_manifest.record_count
                    self._mark_reused_manifest(
                        job_id=job_id,
                        version_id=version.version_id,
                        active_manifest_index_id=active_index_id,
                    )
                    progress_updater.update(
                        ProgressUpdate(
                            runtime_status="completed",
                            current_step=IndexingJobStep.COMPLETED.value,
                            progress_message="reused active manifest",
                            progress_completed_steps=resolve_stage_progress(IndexingJobStep.COMPLETED.value),
                            progress_total_steps=DEFAULT_PROGRESS_TOTAL_STEPS,
                            lock_token=lock_token,
                            latest_manifest_index_id=active_index_id,
                            active_manifest_index_id=active_index_id,
                            chunk_count=chunk_count,
                            embedding_count=embedding_count,
                            embedding_batch_count=embedding_batch_count,
                            embedding_batches_completed=embedding_batch_count,
                            vector_mapping_count=vector_mapping_count,
                            embedding_duration_ms=embedding_duration_ms,
                            total_duration_ms=self._elapsed_ms(started_at),
                            completed=True,
                        ),
                        force=True,
                    )
                    self._deps.version_lock.release(version.version_id, lock_token)
                    return IndexingJobRunResult(
                        job_id=job_id,
                        root_job_id=root_job_id or job_id,
                        retry_of_job_id=failed_job.job_id if failed_job is not None else None,
                        attempt=attempt,
                        version_id=version.version_id,
                        latest_manifest_index_id=active_index_id,
                        active_manifest_index_id=active_index_id,
                    )

            self._deps.version_lock.renew(version.version_id, lock_token)
            current_step = IndexingJobStep.FAISS_BUILDING
            progress_updater.update(
                ProgressUpdate(
                    runtime_status="running",
                    current_step=current_step.value,
                    progress_message="building FAISS index",
                    progress_completed_steps=resolve_stage_progress(current_step.value),
                    progress_total_steps=DEFAULT_PROGRESS_TOTAL_STEPS,
                    lock_token=lock_token,
                    chunk_count=chunk_count,
                    embedding_count=embedding_count,
                    embedding_batch_count=embedding_batch_count,
                    embedding_batches_completed=embedding_batch_count,
                    embedding_duration_ms=embedding_duration_ms,
                ),
                force=True,
            )
            faiss_started_at = self._now()
            embeddings_for_build = [
                {
                    "chunk_id": item.chunk_id,
                    "content_hash": item.content_hash,
                    "provider": item.provider,
                    "model": item.model,
                    "dimension": item.dimension,
                    "vector": list(item.vector_json),
                    "vector_checksum": item.vector_checksum,
                }
                for item in persisted_embeddings
            ]
            from app.risk_knowledge.embedding.schemas import EmbeddingVectorResult

            build_inputs = [EmbeddingVectorResult.model_validate(item) for item in embeddings_for_build]
            index_id = build_faiss_index_id(version.version_id, job_id)
            with self._deps.session_factory() as db:
                store = FaissIndexStore(artifact_root=self._deps.artifact_root, db=db)
                built = store.build_index(
                    build_inputs,
                    FaissIndexManifestDraft(
                        index_id=index_id,
                        kb_id=version.kb_id,
                        version_id=version.version_id,
                        embedding_provider=build_inputs[0].provider,
                        embedding_model=build_inputs[0].model,
                        embedding_dimension=build_inputs[0].dimension,
                        job_id=job_id,
                        index_type="flat_l2",
                        distance_metric="l2",
                        chunk_content_pairs=[(item.chunk_id, item.content_hash) for item in build_inputs],
                    ),
                )
                saved = store.save_index(built)
                saved_manifest = saved.manifest

            vector_mapping_count = len(saved.vector_mappings)
            faiss_duration_ms = self._elapsed_ms(faiss_started_at)
            self._deps.version_lock.renew(version.version_id, lock_token)
            current_step = IndexingJobStep.MANIFEST_PERSISTING
            progress_updater.update(
                ProgressUpdate(
                    runtime_status="running",
                    current_step=current_step.value,
                    progress_message="manifest persisted",
                    progress_completed_steps=resolve_stage_progress(current_step.value),
                    progress_total_steps=DEFAULT_PROGRESS_TOTAL_STEPS,
                    lock_token=lock_token,
                    latest_manifest_index_id=saved_manifest.index_id,
                    chunk_count=chunk_count,
                    embedding_count=embedding_count,
                    embedding_batch_count=embedding_batch_count,
                    embedding_batches_completed=embedding_batch_count,
                    vector_mapping_count=vector_mapping_count,
                    embedding_duration_ms=embedding_duration_ms,
                    faiss_duration_ms=faiss_duration_ms,
                ),
                force=True,
            )

            if self._lose_lock_before_activation:
                self._deps.version_lock.release(version.version_id, lock_token)

            self._deps.version_lock.renew(version.version_id, lock_token)
            current_step = IndexingJobStep.ACTIVATING_MANIFEST
            progress_updater.update(
                ProgressUpdate(
                    runtime_status="running",
                    current_step=current_step.value,
                    progress_message="activating manifest",
                    progress_completed_steps=resolve_stage_progress(current_step.value),
                    progress_total_steps=DEFAULT_PROGRESS_TOTAL_STEPS,
                    lock_token=lock_token,
                    latest_manifest_index_id=saved_manifest.index_id,
                    chunk_count=chunk_count,
                    embedding_count=embedding_count,
                    embedding_batch_count=embedding_batch_count,
                    embedding_batches_completed=embedding_batch_count,
                    vector_mapping_count=vector_mapping_count,
                    embedding_duration_ms=embedding_duration_ms,
                    faiss_duration_ms=faiss_duration_ms,
                ),
                force=True,
            )
            active_manifest_id = self._activate_manifest(
                job_id=job_id,
                version_id=version.version_id,
                manifest_index_id=saved_manifest.index_id,
            )
            progress_updater.update(
                ProgressUpdate(
                    runtime_status="completed",
                    current_step=IndexingJobStep.COMPLETED.value,
                    progress_message="manifest activated",
                    progress_completed_steps=resolve_stage_progress(IndexingJobStep.COMPLETED.value),
                    progress_total_steps=DEFAULT_PROGRESS_TOTAL_STEPS,
                    lock_token=lock_token,
                    latest_manifest_index_id=active_manifest_id,
                    active_manifest_index_id=active_manifest_id,
                    chunk_count=chunk_count,
                    embedding_count=embedding_count,
                    embedding_batch_count=embedding_batch_count,
                    embedding_batches_completed=embedding_batch_count,
                    vector_mapping_count=vector_mapping_count,
                    embedding_duration_ms=embedding_duration_ms,
                    faiss_duration_ms=faiss_duration_ms,
                    total_duration_ms=self._elapsed_ms(started_at),
                    completed=True,
                ),
                force=True,
            )
            self._deps.version_lock.release(version.version_id, lock_token)
            return IndexingJobRunResult(
                job_id=job_id,
                root_job_id=root_job_id or job_id,
                retry_of_job_id=failed_job.job_id if failed_job is not None else None,
                attempt=attempt,
                version_id=version.version_id,
                latest_manifest_index_id=active_manifest_id,
                active_manifest_index_id=active_manifest_id,
            )
        except Exception as exc:
            failure_step = self._resolve_failure_step(progress_updater, current_step)
            self._mark_failed(
                job_id=job_id,
                version_id=version.version_id,
                error_message=str(exc),
                current_step=failure_step,
            )
            try:
                progress_updater.update(
                    ProgressUpdate(
                        runtime_status="failed",
                        current_step=failure_step.value,
                        progress_message=f"failed during {failure_step.value}: {exc}",
                        progress_completed_steps=resolve_stage_progress(failure_step.value),
                        progress_total_steps=DEFAULT_PROGRESS_TOTAL_STEPS,
                        lock_token=lock_token,
                        error_code=exc.__class__.__name__,
                        error_message=str(exc),
                        chunk_count=chunk_count or None,
                        embedding_count=embedding_count or None,
                        embedding_batch_count=embedding_batch_count or None,
                        embedding_batches_completed=embedding_batch_count or None,
                        vector_mapping_count=vector_mapping_count or None,
                        embedding_duration_ms=embedding_duration_ms,
                        faiss_duration_ms=faiss_duration_ms,
                        total_duration_ms=self._elapsed_ms(started_at),
                        completed=True,
                    ),
                    force=True,
                )
            finally:
                if lock_token is not None:
                    try:
                        self._deps.version_lock.release(version.version_id, lock_token)
                    except Exception:
                        pass
            raise

    def _validate_version_status(self, version: KnowledgeDocumentVersion, trigger: IndexingJobTrigger) -> None:
        allowed = {DocumentVersionStatus.PARSED}
        if trigger in {IndexingJobTrigger.REBUILD_FROM_PARSED, IndexingJobTrigger.REBUILD_FROM_PERSISTED_CHUNKS}:
            allowed = {
                DocumentVersionStatus.PARSED,
                DocumentVersionStatus.INDEXED,
                DocumentVersionStatus.ACTIVE,
                DocumentVersionStatus.FAILED,
            }
        if version.status not in allowed:
            raise IndexingJobNotRetryableError(
                f"version status {version.status.value} is not allowed for trigger {trigger.value}"
            )

    def _create_job(
        self,
        *,
        job_id: str,
        document: KnowledgeDocument,
        version: KnowledgeDocumentVersion,
        trigger: IndexingJobTrigger,
        attempt: int,
        root_job_id: str,
        retry_of_job_id: str | None,
    ) -> KnowledgeIngestJob:
        with self._deps.session_factory() as db:
            repo = SqlAlchemyKnowledgeIngestJobRepository(db)
            existing = repo.get(job_id)
            if existing is not None:
                return existing
            now = self._now()
            job = repo.create(
                KnowledgeIngestJob(
                    job_id=job_id,
                    kb_id=document.kb_id,
                    doc_id=document.doc_id,
                    version_id=version.version_id,
                    status=IndexingJobStatus.PENDING,
                    current_step=IndexingJobStep.QUEUED,
                    error_message=None,
                    trigger=trigger,
                    attempt=attempt,
                    max_attempts=settings.risk_knowledge_indexing_max_retries,
                    root_job_id=root_job_id,
                    retry_of_job_id=retry_of_job_id,
                    started_at=now,
                    completed_at=None,
                    last_heartbeat_at=now,
                    latest_manifest_index_id=None,
                    active_manifest_index_id=None,
                )
            )
            db.commit()
            return job

    def _transition_version_running(self, version_id: str, trigger: IndexingJobTrigger, job_id: str) -> None:
        with self._deps.session_factory() as db:
            repo = SqlAlchemyKnowledgeDocumentRepository(db)
            version = repo.get_version(version_id)
            if version is None:
                raise ValueError(f"document version not found: {version_id}")
            next_status = (
                DocumentVersionStatus.REINDEXING
                if trigger in {IndexingJobTrigger.REBUILD_FROM_PARSED, IndexingJobTrigger.REBUILD_FROM_PERSISTED_CHUNKS}
                else DocumentVersionStatus.INDEXING
            )
            repo.update_version(version.model_copy(update={"status": next_status, "last_job_id": job_id}))
            db.commit()

    def _list_chunk_ids(self, version_id: str) -> list[str]:
        with self._deps.session_factory() as db:
            repo = SqlAlchemyKnowledgeChunkRepository(db)
            return [item.chunk_id for item in repo.list_by_version(version_id)]

    def _activate_manifest(self, *, job_id: str, version_id: str, manifest_index_id: str) -> str:
        with self._deps.session_factory() as db:
            manifest_repo = SqlAlchemyFaissIndexRepository(db)
            doc_repo = SqlAlchemyKnowledgeDocumentRepository(db)
            job_repo = SqlAlchemyKnowledgeIngestJobRepository(db)
            document_service = DocumentService(doc_repo)
            manifest = manifest_repo.activate_manifest(version_id=version_id, index_id=manifest_index_id)
            version = doc_repo.get_version(version_id)
            if version is None:
                raise ValueError(f"document version not found: {version_id}")
            indexed_version = doc_repo.update_version(
                version.model_copy(
                    update={
                        "status": DocumentVersionStatus.INDEXED,
                        "latest_manifest_index_id": manifest.index_id,
                        "active_manifest_index_id": manifest.index_id,
                        "last_job_id": job_id,
                    }
                )
            )
            document_service.activate_version(indexed_version.version_id)
            job = job_repo.get(job_id)
            if job is None:
                raise ValueError(f"ingest job not found: {job_id}")
            job_repo.update(
                job.model_copy(
                    update={
                        "status": IndexingJobStatus.COMPLETED,
                        "current_step": IndexingJobStep.COMPLETED,
                        "completed_at": self._now(),
                        "last_heartbeat_at": self._now(),
                        "latest_manifest_index_id": manifest.index_id,
                        "active_manifest_index_id": manifest.index_id,
                    }
                )
            )
            db.commit()
            return manifest.index_id

    def _mark_reused_manifest(self, *, job_id: str, version_id: str, active_manifest_index_id: str) -> None:
        with self._deps.session_factory() as db:
            doc_repo = SqlAlchemyKnowledgeDocumentRepository(db)
            job_repo = SqlAlchemyKnowledgeIngestJobRepository(db)
            document_service = DocumentService(doc_repo)
            version = doc_repo.get_version(version_id)
            if version is None:
                raise ValueError(f"document version not found: {version_id}")
            indexed_version = doc_repo.update_version(
                version.model_copy(
                    update={
                        "status": DocumentVersionStatus.INDEXED,
                        "latest_manifest_index_id": active_manifest_index_id,
                        "active_manifest_index_id": active_manifest_index_id,
                        "last_job_id": job_id,
                    }
                )
            )
            document_service.activate_version(indexed_version.version_id)
            job = job_repo.get(job_id)
            if job is None:
                raise ValueError(f"ingest job not found: {job_id}")
            job_repo.update(
                job.model_copy(
                    update={
                        "status": IndexingJobStatus.COMPLETED,
                        "current_step": IndexingJobStep.COMPLETED,
                        "completed_at": self._now(),
                        "last_heartbeat_at": self._now(),
                        "latest_manifest_index_id": active_manifest_index_id,
                        "active_manifest_index_id": active_manifest_index_id,
                    }
                )
            )
            db.commit()

    def _mark_failed(
        self,
        *,
        job_id: str,
        version_id: str,
        error_message: str,
        current_step: IndexingJobStep,
    ) -> None:
        with self._deps.session_factory() as db:
            doc_repo = SqlAlchemyKnowledgeDocumentRepository(db)
            job_repo = SqlAlchemyKnowledgeIngestJobRepository(db)
            version = doc_repo.get_version(version_id)
            if version is not None:
                doc_repo.update_version(version.model_copy(update={"status": DocumentVersionStatus.FAILED}))
            job = job_repo.get(job_id)
            if job is not None:
                now = self._now()
                job_repo.update(
                    job.model_copy(
                        update={
                            "status": IndexingJobStatus.FAILED,
                            "current_step": current_step,
                            "error_message": error_message,
                            "completed_at": now,
                            "last_heartbeat_at": now,
                        }
                    )
                )
            db.commit()

    def _build_progress_updater(
        self,
        *,
        job: KnowledgeIngestJob,
        document: KnowledgeDocument,
        version: KnowledgeDocumentVersion,
    ) -> IndexingProgressUpdater:
        return IndexingProgressUpdater(
            job=job,
            document=document,
            version=version,
            redis_state_store=self._deps.redis_state_store,
            session_factory=self._deps.session_factory,
        )

    def _build_embedding_progress_callback(
        self,
        *,
        progress_updater: IndexingProgressUpdater,
        lock_token: str,
        chunk_count: int,
    ) -> Callable[[int, int], None]:
        def _callback(completed_batches: int, total_batches: int) -> None:
            progress_updater.update(
                ProgressUpdate(
                    runtime_status="running",
                    current_step=IndexingJobStep.EMBEDDING.value,
                    progress_message=f"embedding batch {completed_batches} / {total_batches}",
                    progress_completed_steps=resolve_stage_progress(IndexingJobStep.EMBEDDING.value),
                    progress_total_steps=DEFAULT_PROGRESS_TOTAL_STEPS,
                    lock_token=lock_token,
                    chunk_count=chunk_count,
                    embedding_batch_count=total_batches,
                    embedding_batches_completed=completed_batches,
                )
            )

        return _callback

    def _embedding_batch_count(self, item_count: int) -> int:
        if item_count <= 0:
            return 0
        batch_size = getattr(self._deps.embedding_provider, "max_batch_size", None)
        if batch_size is None or batch_size <= 0:
            return 1
        return (item_count + batch_size - 1) // batch_size

    @staticmethod
    def _resolve_failure_step(
        progress_updater: IndexingProgressUpdater,
        fallback_step: IndexingJobStep,
    ) -> IndexingJobStep:
        state = progress_updater.get_runtime_state()
        if state is None:
            return fallback_step
        try:
            return IndexingJobStep(state.current_step)
        except ValueError:
            return fallback_step

    @staticmethod
    def _elapsed_ms(started_at: datetime | None) -> int | None:
        if started_at is None:
            return None
        return max(0, int((datetime.now(UTC).replace(tzinfo=None) - started_at).total_seconds() * 1000))

    @staticmethod
    def _resolve_file_size_bytes(file_uri: str) -> int | None:
        try:
            return Path(file_uri).stat().st_size
        except OSError:
            return None

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)
