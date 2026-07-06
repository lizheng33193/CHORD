"""Public exports for the M4 memory contract layer."""

from app.services.memory.candidates import MemoryCandidate
from app.services.memory.contracts import (
    MemoryAuthorityLevel,
    MemorySourceType,
    MemoryUseDecision,
    MemoryUsePurpose,
)
from app.services.memory.dedupe import build_memory_dedupe_key, normalize_memory_content
from app.services.memory.isolation import validate_memory_use
from app.services.memory.policy import (
    AUDIT_EVENT_ALLOWED,
    AUDIT_EVENT_FORBIDDEN,
    PROFILE_RESULT_ALLOWED,
    PROFILE_RESULT_FORBIDDEN,
    RISK_QA_ALLOWED,
    RISK_QA_FORBIDDEN,
    SQL_CASE_ALLOWED,
    SQL_CASE_FORBIDDEN,
    SQL_ERROR_ALLOWED,
    SQL_ERROR_FORBIDDEN,
    USER_PREFERENCE_ALLOWED,
    USER_PREFERENCE_FORBIDDEN,
)
from app.services.memory.records import (
    MemoryRecordDraft,
    MemoryWriteDecision,
    MemoryWriteRejectReason,
    MemoryWriteStatus,
)
from app.services.memory.redaction import MemoryRedactionResult, redact_memory_content
from app.services.memory.store_adapter import (
    InMemoryMemoryStoreAdapter,
    MemoryStoreAdapter,
    SQLiteV1MemoryStoreAdapter,
)
from app.services.memory.write_gate import MemoryWriteGate

__all__ = [
    "AUDIT_EVENT_ALLOWED",
    "AUDIT_EVENT_FORBIDDEN",
    "build_memory_dedupe_key",
    "InMemoryMemoryStoreAdapter",
    "MemoryRecordDraft",
    "MemoryAuthorityLevel",
    "MemoryCandidate",
    "MemoryRedactionResult",
    "MemorySourceType",
    "MemoryUseDecision",
    "MemoryUsePurpose",
    "MemoryStoreAdapter",
    "MemoryWriteDecision",
    "MemoryWriteGate",
    "MemoryWriteRejectReason",
    "MemoryWriteStatus",
    "normalize_memory_content",
    "PROFILE_RESULT_ALLOWED",
    "PROFILE_RESULT_FORBIDDEN",
    "redact_memory_content",
    "RISK_QA_ALLOWED",
    "RISK_QA_FORBIDDEN",
    "SQLiteV1MemoryStoreAdapter",
    "SQL_CASE_ALLOWED",
    "SQL_CASE_FORBIDDEN",
    "SQL_ERROR_ALLOWED",
    "SQL_ERROR_FORBIDDEN",
    "USER_PREFERENCE_ALLOWED",
    "USER_PREFERENCE_FORBIDDEN",
    "validate_memory_use",
]
