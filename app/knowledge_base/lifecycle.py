"""Lifecycle rules for M2D knowledge-base versions and ingest jobs."""

from __future__ import annotations

from app.knowledge_base.errors import InvalidKnowledgeBaseStateTransition
from app.knowledge_base.schemas import DocumentVersionStatus, IngestJobStatus

PROCESSING_VERSION_STATUSES = {
    DocumentVersionStatus.INDEXING,
    DocumentVersionStatus.REINDEXING,
}

PROCESSING_JOB_STATUSES = {
    IngestJobStatus.PENDING,
    IngestJobStatus.RUNNING,
}

_VERSION_TRANSITIONS: dict[DocumentVersionStatus, set[DocumentVersionStatus]] = {
    DocumentVersionStatus.PARSED: {DocumentVersionStatus.INDEXING, DocumentVersionStatus.REINDEXING, DocumentVersionStatus.FAILED},
    DocumentVersionStatus.INDEXING: {DocumentVersionStatus.INDEXED, DocumentVersionStatus.FAILED},
    DocumentVersionStatus.INDEXED: {DocumentVersionStatus.ACTIVE, DocumentVersionStatus.REINDEXING, DocumentVersionStatus.FAILED},
    DocumentVersionStatus.ACTIVE: {DocumentVersionStatus.REINDEXING, DocumentVersionStatus.DEPRECATED},
    DocumentVersionStatus.REINDEXING: {DocumentVersionStatus.INDEXED, DocumentVersionStatus.FAILED},
    DocumentVersionStatus.FAILED: {DocumentVersionStatus.REINDEXING},
    DocumentVersionStatus.DEPRECATED: {DocumentVersionStatus.DELETED},
    DocumentVersionStatus.DELETED: set(),
}

_JOB_TRANSITIONS: dict[IngestJobStatus, set[IngestJobStatus]] = {
    IngestJobStatus.PENDING: {IngestJobStatus.RUNNING, IngestJobStatus.CANCELED, IngestJobStatus.FAILED},
    IngestJobStatus.RUNNING: {IngestJobStatus.COMPLETED, IngestJobStatus.FAILED, IngestJobStatus.CANCELED},
    IngestJobStatus.COMPLETED: set(),
    IngestJobStatus.FAILED: set(),
    IngestJobStatus.CANCELED: set(),
}


def can_transition_version(
    current_status: DocumentVersionStatus,
    next_status: DocumentVersionStatus,
) -> bool:
    return next_status in _VERSION_TRANSITIONS.get(current_status, set())


def assert_version_transition(
    current_status: DocumentVersionStatus,
    next_status: DocumentVersionStatus,
) -> None:
    if not can_transition_version(current_status, next_status):
        raise InvalidKnowledgeBaseStateTransition(
            f"invalid document-version transition: {current_status.value} -> {next_status.value}"
        )


def can_transition_job(current_status: IngestJobStatus, next_status: IngestJobStatus) -> bool:
    return next_status in _JOB_TRANSITIONS.get(current_status, set())


def assert_job_transition(current_status: IngestJobStatus, next_status: IngestJobStatus) -> None:
    if not can_transition_job(current_status, next_status):
        raise InvalidKnowledgeBaseStateTransition(
            f"invalid ingest-job transition: {current_status.value} -> {next_status.value}"
        )
