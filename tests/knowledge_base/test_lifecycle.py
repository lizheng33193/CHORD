from __future__ import annotations

import pytest

from app.knowledge_base.errors import InvalidKnowledgeBaseStateTransition
from app.knowledge_base.lifecycle import (
    assert_job_transition,
    assert_version_transition,
    can_transition_job,
    can_transition_version,
)
from app.knowledge_base.schemas import DocumentVersionStatus, IngestJobStatus


@pytest.mark.parametrize(
    ("current_status", "next_status"),
    [
        (DocumentVersionStatus.UPLOADED, DocumentVersionStatus.PARSING),
        (DocumentVersionStatus.PARSING, DocumentVersionStatus.PARSED),
        (DocumentVersionStatus.PARSED, DocumentVersionStatus.CHUNKING),
        (DocumentVersionStatus.CHUNKING, DocumentVersionStatus.EMBEDDING),
        (DocumentVersionStatus.EMBEDDING, DocumentVersionStatus.INDEXING),
        (DocumentVersionStatus.INDEXING, DocumentVersionStatus.INDEXED),
        (DocumentVersionStatus.INDEXED, DocumentVersionStatus.ACTIVE),
        (DocumentVersionStatus.ACTIVE, DocumentVersionStatus.REINDEXING),
        (DocumentVersionStatus.REINDEXING, DocumentVersionStatus.INDEXED),
        (DocumentVersionStatus.ACTIVE, DocumentVersionStatus.DEPRECATED),
        (DocumentVersionStatus.PARSING, DocumentVersionStatus.FAILED),
    ],
)
def test_version_lifecycle_allows_expected_transitions(
    current_status: DocumentVersionStatus,
    next_status: DocumentVersionStatus,
) -> None:
    assert can_transition_version(current_status, next_status) is True
    assert_version_transition(current_status, next_status)


@pytest.mark.parametrize(
    ("current_status", "next_status"),
    [
        (DocumentVersionStatus.UPLOADED, DocumentVersionStatus.ACTIVE),
        (DocumentVersionStatus.FAILED, DocumentVersionStatus.ACTIVE),
        (DocumentVersionStatus.INDEXED, DocumentVersionStatus.FAILED),
        (DocumentVersionStatus.ACTIVE, DocumentVersionStatus.DELETED),
        (DocumentVersionStatus.DEPRECATED, DocumentVersionStatus.INDEXING),
        (DocumentVersionStatus.DELETED, DocumentVersionStatus.ACTIVE),
    ],
)
def test_version_lifecycle_rejects_invalid_transitions(
    current_status: DocumentVersionStatus,
    next_status: DocumentVersionStatus,
) -> None:
    assert can_transition_version(current_status, next_status) is False
    with pytest.raises(InvalidKnowledgeBaseStateTransition):
        assert_version_transition(current_status, next_status)


@pytest.mark.parametrize(
    ("current_status", "next_status"),
    [
        (IngestJobStatus.UPLOADED, IngestJobStatus.PARSING),
        (IngestJobStatus.PARSING, IngestJobStatus.PARSED),
        (IngestJobStatus.PARSED, IngestJobStatus.CHUNKING),
        (IngestJobStatus.CHUNKING, IngestJobStatus.EMBEDDING),
        (IngestJobStatus.EMBEDDING, IngestJobStatus.INDEXING),
        (IngestJobStatus.INDEXING, IngestJobStatus.INDEXED),
        (IngestJobStatus.INDEXED, IngestJobStatus.ACTIVE),
        (IngestJobStatus.ACTIVE, IngestJobStatus.REINDEXING),
        (IngestJobStatus.REINDEXING, IngestJobStatus.INDEXED),
        (IngestJobStatus.EMBEDDING, IngestJobStatus.FAILED),
    ],
)
def test_job_lifecycle_allows_expected_transitions(
    current_status: IngestJobStatus,
    next_status: IngestJobStatus,
) -> None:
    assert can_transition_job(current_status, next_status) is True
    assert_job_transition(current_status, next_status)


@pytest.mark.parametrize(
    ("current_status", "next_status"),
    [
        (IngestJobStatus.UPLOADED, IngestJobStatus.ACTIVE),
        (IngestJobStatus.FAILED, IngestJobStatus.ACTIVE),
        (IngestJobStatus.INDEXED, IngestJobStatus.FAILED),
        (IngestJobStatus.ACTIVE, IngestJobStatus.DELETED),
        (IngestJobStatus.DEPRECATED, IngestJobStatus.INDEXING),
        (IngestJobStatus.DELETED, IngestJobStatus.ACTIVE),
    ],
)
def test_job_lifecycle_rejects_invalid_transitions(
    current_status: IngestJobStatus,
    next_status: IngestJobStatus,
) -> None:
    assert can_transition_job(current_status, next_status) is False
    with pytest.raises(InvalidKnowledgeBaseStateTransition):
        assert_job_transition(current_status, next_status)
