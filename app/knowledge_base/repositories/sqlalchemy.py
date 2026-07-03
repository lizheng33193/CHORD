"""SQLAlchemy repositories for durable M2D knowledge-base records."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge_base.models import (
    KnowledgeBaseModel,
    KnowledgeDocumentModel,
    KnowledgeDocumentVersionModel,
    KnowledgeIngestArtifactModel,
    KnowledgeIngestJobModel,
    KnowledgeIngestJobControlModel,
    KnowledgeIngestJobRuntimeStateModel,
)
from app.knowledge_base.schemas import (
    KnowledgeBase,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    KnowledgeIngestArtifact,
    KnowledgeIngestJob,
    KnowledgeIngestJobControl,
    KnowledgeIngestJobRuntimeState,
)


class SqlAlchemyKnowledgeBaseRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, kb: KnowledgeBase) -> KnowledgeBase:
        model = KnowledgeBaseModel(
            kb_id=kb.kb_id,
            kb_name=kb.kb_name,
            kb_type=kb.kb_type.value,
            description=kb.description,
            status=kb.status.value,
            index_alias=kb.index_alias,
        )
        self._db.add(model)
        self._db.flush()
        self._db.refresh(model)
        return _to_kb(model)

    def get(self, kb_id: str) -> KnowledgeBase | None:
        model = self._db.scalar(select(KnowledgeBaseModel).where(KnowledgeBaseModel.kb_id == kb_id))
        return _to_kb(model) if model is not None else None

    def list(self) -> list[KnowledgeBase]:
        items = self._db.scalars(select(KnowledgeBaseModel).order_by(KnowledgeBaseModel.kb_id.asc())).all()
        return [_to_kb(item) for item in items]

    def update(self, kb: KnowledgeBase) -> KnowledgeBase:
        model = self._db.scalar(select(KnowledgeBaseModel).where(KnowledgeBaseModel.kb_id == kb.kb_id))
        if model is None:
            raise ValueError(f"knowledge base not found: {kb.kb_id}")
        model.kb_name = kb.kb_name
        model.kb_type = kb.kb_type.value
        model.description = kb.description
        model.status = kb.status.value
        model.index_alias = kb.index_alias
        self._db.flush()
        self._db.refresh(model)
        return _to_kb(model)


class SqlAlchemyKnowledgeDocumentRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create_document(self, document: KnowledgeDocument) -> KnowledgeDocument:
        model = KnowledgeDocumentModel(
            doc_id=document.doc_id,
            kb_id=document.kb_id,
            doc_title=document.doc_title,
            doc_name=document.doc_name,
            source_type=document.source_type.value,
            source_uri=document.source_uri,
            current_version_id=document.current_version_id,
            status=document.status.value,
            permission_scope=document.permission_scope.value,
        )
        self._db.add(model)
        self._db.flush()
        self._db.refresh(model)
        return _to_document(model)

    def get_document(self, doc_id: str) -> KnowledgeDocument | None:
        model = self._db.scalar(select(KnowledgeDocumentModel).where(KnowledgeDocumentModel.doc_id == doc_id))
        return _to_document(model) if model is not None else None

    def list_documents(self, kb_id: str) -> list[KnowledgeDocument]:
        items = self._db.scalars(
            select(KnowledgeDocumentModel)
            .where(KnowledgeDocumentModel.kb_id == kb_id)
            .order_by(KnowledgeDocumentModel.doc_id.asc())
        ).all()
        return [_to_document(item) for item in items]

    def update_document(self, document: KnowledgeDocument) -> KnowledgeDocument:
        model = self._db.scalar(select(KnowledgeDocumentModel).where(KnowledgeDocumentModel.doc_id == document.doc_id))
        if model is None:
            raise ValueError(f"document not found: {document.doc_id}")
        model.kb_id = document.kb_id
        model.doc_title = document.doc_title
        model.doc_name = document.doc_name
        model.source_type = document.source_type.value
        model.source_uri = document.source_uri
        model.current_version_id = document.current_version_id
        model.status = document.status.value
        model.permission_scope = document.permission_scope.value
        self._db.flush()
        self._db.refresh(model)
        return _to_document(model)

    def create_version(self, version: KnowledgeDocumentVersion) -> KnowledgeDocumentVersion:
        model = KnowledgeDocumentVersionModel(
            version_id=version.version_id,
            doc_id=version.doc_id,
            kb_id=version.kb_id,
            version=version.version,
            file_hash=version.file_hash,
            file_uri=version.file_uri,
            parser_version=version.parser_version,
            chunker_version=version.chunker_version,
            embedding_model=version.embedding_model,
            embedding_dim=version.embedding_dim,
            index_name=version.index_name,
            status=version.status.value,
            latest_manifest_index_id=version.latest_manifest_index_id,
            active_manifest_index_id=version.active_manifest_index_id,
            last_job_id=version.last_job_id,
        )
        self._db.add(model)
        self._db.flush()
        self._db.refresh(model)
        return _to_version(model)

    def get_version(self, version_id: str) -> KnowledgeDocumentVersion | None:
        model = self._db.scalar(
            select(KnowledgeDocumentVersionModel).where(KnowledgeDocumentVersionModel.version_id == version_id)
        )
        return _to_version(model) if model is not None else None

    def list_versions(self, doc_id: str) -> list[KnowledgeDocumentVersion]:
        items = self._db.scalars(
            select(KnowledgeDocumentVersionModel)
            .where(KnowledgeDocumentVersionModel.doc_id == doc_id)
            .order_by(KnowledgeDocumentVersionModel.version.asc())
        ).all()
        return [_to_version(item) for item in items]

    def update_version(self, version: KnowledgeDocumentVersion) -> KnowledgeDocumentVersion:
        model = self._db.scalar(
            select(KnowledgeDocumentVersionModel).where(KnowledgeDocumentVersionModel.version_id == version.version_id)
        )
        if model is None:
            raise ValueError(f"document version not found: {version.version_id}")
        model.doc_id = version.doc_id
        model.kb_id = version.kb_id
        model.version = version.version
        model.file_hash = version.file_hash
        model.file_uri = version.file_uri
        model.parser_version = version.parser_version
        model.chunker_version = version.chunker_version
        model.embedding_model = version.embedding_model
        model.embedding_dim = version.embedding_dim
        model.index_name = version.index_name
        model.status = version.status.value
        model.latest_manifest_index_id = version.latest_manifest_index_id
        model.active_manifest_index_id = version.active_manifest_index_id
        model.last_job_id = version.last_job_id
        self._db.flush()
        self._db.refresh(model)
        return _to_version(model)


class SqlAlchemyKnowledgeIngestJobRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, job: KnowledgeIngestJob) -> KnowledgeIngestJob:
        model = KnowledgeIngestJobModel(
            job_id=job.job_id,
            kb_id=job.kb_id,
            doc_id=job.doc_id,
            version_id=job.version_id,
            status=job.status.value,
            current_step=job.current_step.value,
            error_message=job.error_message,
            trigger=job.trigger.value,
            attempt=job.attempt,
            max_attempts=job.max_attempts,
            root_job_id=job.root_job_id,
            retry_of_job_id=job.retry_of_job_id,
            started_at=job.started_at,
            completed_at=job.completed_at,
            last_heartbeat_at=job.last_heartbeat_at,
            latest_manifest_index_id=job.latest_manifest_index_id,
            active_manifest_index_id=job.active_manifest_index_id,
        )
        self._db.add(model)
        self._db.flush()
        self._db.refresh(model)
        return _to_job(model)

    def get(self, job_id: str) -> KnowledgeIngestJob | None:
        model = self._db.scalar(select(KnowledgeIngestJobModel).where(KnowledgeIngestJobModel.job_id == job_id))
        return _to_job(model) if model is not None else None

    def update(self, job: KnowledgeIngestJob) -> KnowledgeIngestJob:
        model = self._db.scalar(select(KnowledgeIngestJobModel).where(KnowledgeIngestJobModel.job_id == job.job_id))
        if model is None:
            raise ValueError(f"ingest job not found: {job.job_id}")
        model.status = job.status.value
        model.current_step = job.current_step.value
        model.error_message = job.error_message
        model.trigger = job.trigger.value
        model.attempt = job.attempt
        model.max_attempts = job.max_attempts
        model.root_job_id = job.root_job_id
        model.retry_of_job_id = job.retry_of_job_id
        model.started_at = job.started_at
        model.completed_at = job.completed_at
        model.last_heartbeat_at = job.last_heartbeat_at
        model.latest_manifest_index_id = job.latest_manifest_index_id
        model.active_manifest_index_id = job.active_manifest_index_id
        self._db.flush()
        self._db.refresh(model)
        return _to_job(model)

    def list_by_version(self, version_id: str) -> list[KnowledgeIngestJob]:
        items = self._db.scalars(
            select(KnowledgeIngestJobModel)
            .where(KnowledgeIngestJobModel.version_id == version_id)
            .order_by(KnowledgeIngestJobModel.attempt.desc(), KnowledgeIngestJobModel.created_at.desc())
        ).all()
        return [_to_job(item) for item in items]

    def list_by_statuses(self, statuses: list[str]) -> list[KnowledgeIngestJob]:
        items = self._db.scalars(
            select(KnowledgeIngestJobModel)
            .where(KnowledgeIngestJobModel.status.in_(statuses))
            .order_by(KnowledgeIngestJobModel.created_at.asc(), KnowledgeIngestJobModel.job_id.asc())
        ).all()
        return [_to_job(item) for item in items]


class SqlAlchemyKnowledgeIngestJobControlRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, job_id: str) -> KnowledgeIngestJobControl | None:
        model = self._db.scalar(select(KnowledgeIngestJobControlModel).where(KnowledgeIngestJobControlModel.job_id == job_id))
        return _to_job_control(model) if model is not None else None

    def upsert(self, state: KnowledgeIngestJobControl) -> KnowledgeIngestJobControl:
        model = self._db.scalar(select(KnowledgeIngestJobControlModel).where(KnowledgeIngestJobControlModel.job_id == state.job_id))
        if model is None:
            model = KnowledgeIngestJobControlModel(job_id=state.job_id)
            self._db.add(model)

        model.lease_owner = state.lease_owner
        model.lease_expires_at = state.lease_expires_at
        model.cancel_requested_at = state.cancel_requested_at
        model.stale_detected_at = state.stale_detected_at
        model.stale_reason = state.stale_reason
        self._db.flush()
        self._db.refresh(model)
        return _to_job_control(model)


class SqlAlchemyKnowledgeIngestArtifactRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, artifact: KnowledgeIngestArtifact) -> KnowledgeIngestArtifact:
        model = KnowledgeIngestArtifactModel(
            job_id=artifact.job_id,
            version_id=artifact.version_id,
            artifact_kind=artifact.artifact_kind,
            artifact_path=artifact.artifact_path,
            is_temporary=artifact.is_temporary,
            created_at=artifact.created_at,
            cleaned_at=artifact.cleaned_at,
        )
        self._db.add(model)
        self._db.flush()
        self._db.refresh(model)
        return _to_job_artifact(model)

    def list_by_job(self, job_id: str) -> list[KnowledgeIngestArtifact]:
        items = self._db.scalars(
            select(KnowledgeIngestArtifactModel)
            .where(KnowledgeIngestArtifactModel.job_id == job_id)
            .order_by(KnowledgeIngestArtifactModel.created_at.asc(), KnowledgeIngestArtifactModel.id.asc())
        ).all()
        return [_to_job_artifact(item) for item in items]


class SqlAlchemyKnowledgeIngestJobRuntimeStateRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, job_id: str) -> KnowledgeIngestJobRuntimeState | None:
        model = self._db.scalar(
            select(KnowledgeIngestJobRuntimeStateModel).where(KnowledgeIngestJobRuntimeStateModel.job_id == job_id)
        )
        return _to_runtime_state(model) if model is not None else None

    def upsert(self, state: KnowledgeIngestJobRuntimeState) -> KnowledgeIngestJobRuntimeState:
        model = self._db.scalar(
            select(KnowledgeIngestJobRuntimeStateModel).where(KnowledgeIngestJobRuntimeStateModel.job_id == state.job_id)
        )
        if model is None:
            model = KnowledgeIngestJobRuntimeStateModel(job_id=state.job_id)
            self._db.add(model)

        model.progress_message = state.progress_message
        model.progress_completed_steps = state.progress_completed_steps
        model.progress_total_steps = state.progress_total_steps
        model.file_size_bytes = state.file_size_bytes
        model.page_count = state.page_count
        model.chunk_count = state.chunk_count
        model.embedding_count = state.embedding_count
        model.embedding_batch_count = state.embedding_batch_count
        model.embedding_batches_completed = state.embedding_batches_completed
        model.vector_mapping_count = state.vector_mapping_count
        model.parser_duration_ms = state.parser_duration_ms
        model.embedding_duration_ms = state.embedding_duration_ms
        model.faiss_duration_ms = state.faiss_duration_ms
        model.total_duration_ms = state.total_duration_ms
        self._db.flush()
        self._db.refresh(model)
        return _to_runtime_state(model)


def _to_document(model: KnowledgeDocumentModel) -> KnowledgeDocument:
    return KnowledgeDocument.model_validate(
        {
            "doc_id": model.doc_id,
            "kb_id": model.kb_id,
            "doc_title": model.doc_title,
            "doc_name": model.doc_name,
            "source_type": model.source_type,
            "source_uri": model.source_uri,
            "current_version_id": model.current_version_id,
            "status": model.status,
            "permission_scope": model.permission_scope,
        }
    )


def _to_kb(model: KnowledgeBaseModel) -> KnowledgeBase:
    return KnowledgeBase.model_validate(
        {
            "kb_id": model.kb_id,
            "kb_name": model.kb_name,
            "kb_type": model.kb_type,
            "description": model.description,
            "status": model.status,
            "index_alias": model.index_alias,
        }
    )


def _to_version(model: KnowledgeDocumentVersionModel) -> KnowledgeDocumentVersion:
    return KnowledgeDocumentVersion.model_validate(
        {
            "version_id": model.version_id,
            "doc_id": model.doc_id,
            "kb_id": model.kb_id,
            "version": model.version,
            "file_hash": model.file_hash,
            "file_uri": model.file_uri,
            "parser_version": model.parser_version,
            "chunker_version": model.chunker_version,
            "embedding_model": model.embedding_model,
            "embedding_dim": model.embedding_dim,
            "index_name": model.index_name,
            "status": model.status,
            "latest_manifest_index_id": model.latest_manifest_index_id,
            "active_manifest_index_id": model.active_manifest_index_id,
            "last_job_id": model.last_job_id,
        }
    )


def _to_job(model: KnowledgeIngestJobModel) -> KnowledgeIngestJob:
    status = model.status
    if status == "pending":
        status = "queued"
    return KnowledgeIngestJob.model_validate(
        {
            "job_id": model.job_id,
            "kb_id": model.kb_id,
            "doc_id": model.doc_id,
            "version_id": model.version_id,
            "status": status,
            "current_step": model.current_step,
            "error_message": model.error_message,
            "trigger": model.trigger,
            "attempt": model.attempt,
            "max_attempts": model.max_attempts,
            "root_job_id": model.root_job_id,
            "retry_of_job_id": model.retry_of_job_id,
            "started_at": model.started_at,
            "completed_at": model.completed_at,
            "last_heartbeat_at": model.last_heartbeat_at,
            "latest_manifest_index_id": model.latest_manifest_index_id,
            "active_manifest_index_id": model.active_manifest_index_id,
        }
    )


def _to_job_control(model: KnowledgeIngestJobControlModel) -> KnowledgeIngestJobControl:
    return KnowledgeIngestJobControl.model_validate(
        {
            "job_id": model.job_id,
            "lease_owner": model.lease_owner,
            "lease_expires_at": model.lease_expires_at,
            "cancel_requested_at": model.cancel_requested_at,
            "stale_detected_at": model.stale_detected_at,
            "stale_reason": model.stale_reason,
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        }
    )


def _to_job_artifact(model: KnowledgeIngestArtifactModel) -> KnowledgeIngestArtifact:
    return KnowledgeIngestArtifact.model_validate(
        {
            "job_id": model.job_id,
            "version_id": model.version_id,
            "artifact_kind": model.artifact_kind,
            "artifact_path": model.artifact_path,
            "is_temporary": model.is_temporary,
            "created_at": model.created_at,
            "cleaned_at": model.cleaned_at,
        }
    )


def _to_runtime_state(model: KnowledgeIngestJobRuntimeStateModel) -> KnowledgeIngestJobRuntimeState:
    return KnowledgeIngestJobRuntimeState.model_validate(
        {
            "job_id": model.job_id,
            "progress_message": model.progress_message,
            "progress_completed_steps": model.progress_completed_steps,
            "progress_total_steps": model.progress_total_steps,
            "file_size_bytes": model.file_size_bytes,
            "page_count": model.page_count,
            "chunk_count": model.chunk_count,
            "embedding_count": model.embedding_count,
            "embedding_batch_count": model.embedding_batch_count,
            "embedding_batches_completed": model.embedding_batches_completed,
            "vector_mapping_count": model.vector_mapping_count,
            "parser_duration_ms": model.parser_duration_ms,
            "embedding_duration_ms": model.embedding_duration_ms,
            "faiss_duration_ms": model.faiss_duration_ms,
            "total_duration_ms": model.total_duration_ms,
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        }
    )
