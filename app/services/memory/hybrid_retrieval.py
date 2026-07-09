"""Unified hybrid retrieval runtime for M6B."""

from __future__ import annotations

from dataclasses import replace

from app.core.config import settings
from app.services.memory.context_builder import build_memory_context_bundle
from app.services.memory.fusion import fuse_memory_items
from app.services.memory.observability import (
    SEMANTIC_MEMORY_TRACE_METADATA_KEY,
    ensure_semantic_memory_trace,
    trace_warnings,
)
from app.services.memory.retrieval import MemoryRetrievalRequest, MemoryRetrievalResult, MemoryRetrievalService
from app.services.memory.retrieval_adapter import SQLiteV1MemoryRetrievalAdapter
from app.services.memory.semantic_retrieval import SemanticMemoryRetrievalService
from app.services.orchestrator_agent.memory_store import SQLiteMemoryStore


class HybridMemoryRetrievalService:
    def __init__(self, *, relational_store: SQLiteMemoryStore) -> None:
        self.relational_store = relational_store
        self.fts_service = MemoryRetrievalService(
            SQLiteV1MemoryRetrievalAdapter(db_path=relational_store.db_path)
        )
        self.semantic_service = SemanticMemoryRetrievalService(relational_store=relational_store)

    def retrieve(self, request: MemoryRetrievalRequest) -> MemoryRetrievalResult:
        fts_result = _empty_retrieval_result(request)
        if request.allow_fts:
            fts_request = replace(
                request,
                include_legacy_memory=True,
                allow_vector=False,
                retrieval_mode="fts_only",
            )
            fts_result = self.fts_service.retrieve(fts_request)

        vector_result = _empty_retrieval_result(request)
        if request.allow_vector:
            vector_request = replace(
                request,
                include_legacy_memory=True,
                allow_fts=False,
            )
            vector_result = self.semantic_service.retrieve(vector_request)

        fused_items = fuse_memory_items(
            fts_items=fts_result.items,
            vector_items=vector_result.items,
            max_total_items=request.max_items,
            max_vector_items=request.max_vector_items,
        )
        warnings = tuple(dict.fromkeys([*fts_result.warnings, *vector_result.warnings]))
        trace = ensure_semantic_memory_trace(vector_result.metadata, request)
        trace["fts_candidate_count"] = len(fts_result.items)
        trace["fused_candidate_count"] = len(fused_items)
        trace["warnings"] = trace_warnings(warnings)
        metadata = {
            "fts_item_count": len(fts_result.items),
            "vector_item_count": len(vector_result.items),
            "used_fallback": bool(vector_result.metadata.get("used_fallback", False)),
            "vector_health": vector_result.metadata.get("vector_health"),
            SEMANTIC_MEMORY_TRACE_METADATA_KEY: trace,
        }
        return MemoryRetrievalResult(
            request=request,
            items=fused_items,
            rejected_items=(*fts_result.rejected_items, *vector_result.rejected_items),
            warnings=warnings,
            metadata=metadata,
        )

    def build_context_bundle(self, request: MemoryRetrievalRequest):
        return build_memory_context_bundle(
            self.retrieve(request),
            max_chars=settings.memory_vector_text_max_chars * 2,
        )


def build_hybrid_memory_retrieval_service(
    store: SQLiteMemoryStore | None = None,
) -> HybridMemoryRetrievalService:
    return HybridMemoryRetrievalService(relational_store=store or SQLiteMemoryStore())


def _empty_retrieval_result(request: MemoryRetrievalRequest) -> MemoryRetrievalResult:
    return MemoryRetrievalResult(
        request=request,
        items=(),
        rejected_items=(),
        warnings=(),
        metadata={},
    )
