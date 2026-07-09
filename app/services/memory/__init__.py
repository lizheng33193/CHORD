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
    CONVERSATION_ALLOWED,
    CONVERSATION_FORBIDDEN,
    EVAL_CASE_ALLOWED,
    EVAL_CASE_FORBIDDEN,
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
from app.services.memory.promotion import (
    MemoryPromotionBlockReason,
    MemoryPromotionDecision,
    MemoryPromotionRequest,
    MemoryPromotionStatus,
    MemoryPromotionTarget,
    promotion_request_from_candidate,
    promotion_request_from_retrieved_item,
    validate_memory_promotion,
)
from app.services.memory.records import (
    MemoryRecordDraft,
    MemoryWriteDecision,
    MemoryWriteRejectReason,
    MemoryWriteStatus,
)
from app.services.memory.retrieval import (
    MemoryRejectedRetrievalItem,
    MemoryRetrievalRequest,
    MemoryRetrievalResult,
    MemoryRetrievalService,
    MemoryRetrievedItem,
)
from app.services.memory.retrieval_adapter import (
    InMemoryMemoryRetrievalAdapter,
    MemoryReadableStoreAdapter,
    MemoryStoredRecord,
    SQLiteV1MemoryRetrievalAdapter,
)
from app.services.memory.retrieval_policy import (
    MemoryRetrievalPolicy,
    MemoryRetrievalTaskType,
    resolve_retrieval_policies,
)
from app.services.memory.redaction import MemoryRedactionResult, redact_memory_content
from app.services.memory.store_adapter import (
    InMemoryMemoryStoreAdapter,
    MemoryStoreAdapter,
    SQLiteV1MemoryStoreAdapter,
)
from app.services.memory.write_gate import MemoryWriteGate
from app.services.memory.context_builder import (
    MemoryContextBundle,
    MemoryContextItem,
    build_memory_context_bundle,
)
from app.services.memory.fusion import fuse_memory_items
from app.services.memory.hybrid_retrieval import (
    HybridMemoryRetrievalService,
    build_hybrid_memory_retrieval_service,
)
from app.services.memory.semantic_retrieval import SemanticMemoryRetrievalService
from app.services.memory.vector_index_adapter import (
    MemoryVectorIndex,
    MemoryVectorQueryHit,
    OrchestratorMemoryVectorIndexAdapter,
)
from app.services.memory.observability import (
    EXECUTION_TRACE_SEMANTIC_MEMORY_KEY,
    SEMANTIC_MEMORY_TRACE_HANDOFF_KEY,
    SEMANTIC_MEMORY_TRACE_METADATA_KEY,
    SEMANTIC_MEMORY_TRACE_SUMMARY_METADATA_KEY,
    SemanticMemoryRetrievalTrace,
    SemanticMemoryTraceSummary,
)

__all__ = [
    "AUDIT_EVENT_ALLOWED",
    "AUDIT_EVENT_FORBIDDEN",
    "build_memory_dedupe_key",
    "build_memory_context_bundle",
    "CONVERSATION_ALLOWED",
    "CONVERSATION_FORBIDDEN",
    "EVAL_CASE_ALLOWED",
    "EVAL_CASE_FORBIDDEN",
    "InMemoryMemoryStoreAdapter",
    "InMemoryMemoryRetrievalAdapter",
    "MemoryContextBundle",
    "MemoryContextItem",
    "MemoryReadableStoreAdapter",
    "MemoryRecordDraft",
    "MemoryAuthorityLevel",
    "MemoryCandidate",
    "MemoryPromotionBlockReason",
    "MemoryPromotionDecision",
    "MemoryPromotionRequest",
    "MemoryPromotionStatus",
    "MemoryPromotionTarget",
    "MemoryRedactionResult",
    "MemoryRejectedRetrievalItem",
    "MemoryRetrievalPolicy",
    "MemoryRetrievalRequest",
    "MemoryRetrievalResult",
    "MemoryRetrievalService",
    "MemoryRetrievalTaskType",
    "MemorySourceType",
    "MemoryStoredRecord",
    "MemoryUseDecision",
    "MemoryUsePurpose",
    "MemoryStoreAdapter",
    "MemoryRetrievedItem",
    "MemoryVectorIndex",
    "MemoryVectorQueryHit",
    "MemoryWriteDecision",
    "MemoryWriteGate",
    "MemoryWriteRejectReason",
    "MemoryWriteStatus",
    "HybridMemoryRetrievalService",
    "build_hybrid_memory_retrieval_service",
    "normalize_memory_content",
    "OrchestratorMemoryVectorIndexAdapter",
    "PROFILE_RESULT_ALLOWED",
    "PROFILE_RESULT_FORBIDDEN",
    "promotion_request_from_candidate",
    "promotion_request_from_retrieved_item",
    "redact_memory_content",
    "resolve_retrieval_policies",
    "RISK_QA_ALLOWED",
    "RISK_QA_FORBIDDEN",
    "SEMANTIC_MEMORY_TRACE_HANDOFF_KEY",
    "SEMANTIC_MEMORY_TRACE_METADATA_KEY",
    "SEMANTIC_MEMORY_TRACE_SUMMARY_METADATA_KEY",
    "EXECUTION_TRACE_SEMANTIC_MEMORY_KEY",
    "SemanticMemoryRetrievalTrace",
    "SemanticMemoryTraceSummary",
    "SemanticMemoryRetrievalService",
    "SQLiteV1MemoryRetrievalAdapter",
    "SQLiteV1MemoryStoreAdapter",
    "SQL_CASE_ALLOWED",
    "SQL_CASE_FORBIDDEN",
    "SQL_ERROR_ALLOWED",
    "SQL_ERROR_FORBIDDEN",
    "USER_PREFERENCE_ALLOWED",
    "USER_PREFERENCE_FORBIDDEN",
    "fuse_memory_items",
    "validate_memory_promotion",
    "validate_memory_use",
]
