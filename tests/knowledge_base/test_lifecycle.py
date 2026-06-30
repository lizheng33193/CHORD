from __future__ import annotations

import pytest

from app.knowledge_base.errors import InvalidKnowledgeBaseStateTransition
from app.knowledge_base.lifecycle import assert_job_transition, can_transition_job
from app.knowledge_base.schemas import IngestJobStatus


@pytest.mark.parametrize(
    ("current_status", "next_status"),
    [
        (IngestJobStatus.PENDING, IngestJobStatus.RUNNING),
        (IngestJobStatus.PENDING, IngestJobStatus.FAILED),
        (IngestJobStatus.RUNNING, IngestJobStatus.COMPLETED),
        (IngestJobStatus.RUNNING, IngestJobStatus.FAILED),
        (IngestJobStatus.RUNNING, IngestJobStatus.CANCELED),
    ],
)
def test_job_lifecycle_allows_expected_transitions(current_status, next_status) -> None:
    assert can_transition_job(current_status, next_status) is True
    assert_job_transition(current_status, next_status)


@pytest.mark.parametrize(
    ("current_status", "next_status"),
    [
        (IngestJobStatus.PENDING, IngestJobStatus.COMPLETED),
        (IngestJobStatus.FAILED, IngestJobStatus.RUNNING),
        (IngestJobStatus.COMPLETED, IngestJobStatus.FAILED),
        (IngestJobStatus.CANCELED, IngestJobStatus.RUNNING),
    ],
)
def test_job_lifecycle_rejects_invalid_transitions(current_status, next_status) -> None:
    assert can_transition_job(current_status, next_status) is False
    with pytest.raises(InvalidKnowledgeBaseStateTransition):
        assert_job_transition(current_status, next_status)
