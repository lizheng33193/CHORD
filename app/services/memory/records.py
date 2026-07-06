"""M4-2 write gate records and decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MemoryWriteStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    REDACTED_AND_ACCEPTED = "redacted_and_accepted"
    DEFERRED = "deferred"


class MemoryWriteRejectReason(str, Enum):
    EMPTY_CONTENT = "empty_content"
    MISSING_SCOPE = "missing_scope"
    INVALID_CANDIDATE = "invalid_candidate"
    MISSING_ALLOWED_USE = "missing_allowed_use"
    MISSING_FORBIDDEN_USE = "missing_forbidden_use"
    SECRET_DETECTED = "secret_detected"
    LOW_IMPORTANCE = "low_importance"
    LOW_CONFIDENCE = "low_confidence"
    DUPLICATE = "duplicate"
    STORE_UNAVAILABLE = "store_unavailable"
    POLICY_REJECTED = "policy_rejected"


@dataclass(frozen=True)
class MemoryRecordDraft:
    content: str
    memory_source_type: str
    authority_level: str
    allowed_memory_use: list[str]
    forbidden_memory_use: list[str]
    user_id: str | None
    project_id: str | None
    country: str | None
    session_id: str | None
    source_run_id: str | None
    source_artifact_id: str | None
    evidence_status: str | None
    importance: float
    confidence: float
    status: str
    dedupe_key: str
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryWriteDecision:
    status: MemoryWriteStatus
    accepted: bool
    persisted: bool
    reason: str
    reject_reason: MemoryWriteRejectReason | None = None
    memory_id: str | None = None
    dedupe_key: str | None = None
    redacted: bool = False
    record_draft: MemoryRecordDraft | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
