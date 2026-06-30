"""Lifecycle rules for M2D knowledge-base versions and ingest jobs."""

from __future__ import annotations

from app.knowledge_base.errors import InvalidKnowledgeBaseStateTransition
from app.knowledge_base.schemas import DocumentVersionStatus, IngestJobStatus

PROCESSING_VERSION_STATUSES = {
    DocumentVersionStatus.UPLOADED,
    DocumentVersionStatus.PARSING,
    DocumentVersionStatus.PARSED,
    DocumentVersionStatus.CHUNKING,
    DocumentVersionStatus.EMBEDDING,
    DocumentVersionStatus.INDEXING,
    DocumentVersionStatus.REINDEXING,
}

PROCESSING_JOB_STATUSES = {
    IngestJobStatus.UPLOADED,
    IngestJobStatus.PARSING,
    IngestJobStatus.PARSED,
    IngestJobStatus.CHUNKING,
    IngestJobStatus.EMBEDDING,
    IngestJobStatus.INDEXING,
    IngestJobStatus.REINDEXING,
}

_VERSION_TRANSITIONS: dict[DocumentVersionStatus, set[DocumentVersionStatus]] = {
    DocumentVersionStatus.UPLOADED: {DocumentVersionStatus.PARSING, DocumentVersionStatus.FAILED},
    DocumentVersionStatus.PARSING: {DocumentVersionStatus.PARSED, DocumentVersionStatus.FAILED},
    DocumentVersionStatus.PARSED: {DocumentVersionStatus.CHUNKING, DocumentVersionStatus.FAILED},
    DocumentVersionStatus.CHUNKING: {DocumentVersionStatus.EMBEDDING, DocumentVersionStatus.FAILED},
    DocumentVersionStatus.EMBEDDING: {DocumentVersionStatus.INDEXING, DocumentVersionStatus.FAILED},
    DocumentVersionStatus.INDEXING: {DocumentVersionStatus.INDEXED, DocumentVersionStatus.FAILED},
    DocumentVersionStatus.INDEXED: {DocumentVersionStatus.ACTIVE},
    DocumentVersionStatus.ACTIVE: {DocumentVersionStatus.REINDEXING, DocumentVersionStatus.DEPRECATED},
    DocumentVersionStatus.REINDEXING: {DocumentVersionStatus.INDEXED, DocumentVersionStatus.FAILED},
    DocumentVersionStatus.FAILED: set(),
    DocumentVersionStatus.DEPRECATED: {DocumentVersionStatus.DELETED},
    DocumentVersionStatus.DELETED: set(),
}

_JOB_TRANSITIONS: dict[IngestJobStatus, set[IngestJobStatus]] = {
    IngestJobStatus.UPLOADED: {IngestJobStatus.PARSING, IngestJobStatus.FAILED},
    IngestJobStatus.PARSING: {IngestJobStatus.PARSED, IngestJobStatus.FAILED},
    IngestJobStatus.PARSED: {IngestJobStatus.CHUNKING, IngestJobStatus.FAILED},
    IngestJobStatus.CHUNKING: {IngestJobStatus.EMBEDDING, IngestJobStatus.FAILED},
    IngestJobStatus.EMBEDDING: {IngestJobStatus.INDEXING, IngestJobStatus.FAILED},
    IngestJobStatus.INDEXING: {IngestJobStatus.INDEXED, IngestJobStatus.FAILED},
    IngestJobStatus.INDEXED: {IngestJobStatus.ACTIVE},
    IngestJobStatus.ACTIVE: {IngestJobStatus.REINDEXING, IngestJobStatus.DEPRECATED},
    IngestJobStatus.REINDEXING: {IngestJobStatus.INDEXED, IngestJobStatus.FAILED},
    IngestJobStatus.FAILED: set(),
    IngestJobStatus.DEPRECATED: {IngestJobStatus.DELETED},
    IngestJobStatus.DELETED: set(),
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
