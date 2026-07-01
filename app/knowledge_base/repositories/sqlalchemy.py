"""SQLAlchemy repositories for durable M2D knowledge-base records."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge_base.models import (
    KnowledgeBaseModel,
    KnowledgeDocumentModel,
    KnowledgeDocumentVersionModel,
    KnowledgeIngestJobModel,
)
from app.knowledge_base.schemas import KnowledgeBase, KnowledgeDocument, KnowledgeDocumentVersion, KnowledgeIngestJob


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
    return KnowledgeIngestJob.model_validate(
        {
            "job_id": model.job_id,
            "kb_id": model.kb_id,
            "doc_id": model.doc_id,
            "version_id": model.version_id,
            "status": model.status,
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
