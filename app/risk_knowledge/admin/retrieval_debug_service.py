"""Retrieval-only debug service for M2D-14A admin APIs."""

from __future__ import annotations

from time import perf_counter

from sqlalchemy.orm import Session

from app.risk_knowledge.admin.schemas import (
    DebugRetrieveCandidateResponse,
    DebugRetrieveCandidateScoresResponse,
    DebugRetrieveDiagnosticsResponse,
    DebugRetrieveRequest,
    DebugRetrieveResponse,
    DebugRetrieveScopeResponse,
)
from app.risk_knowledge.retrieval.hybrid_retriever import HybridRiskKnowledgeRetriever
from app.risk_knowledge.retrieval.schemas import RetrievalQuery

_DEFAULT_TEXT_PREVIEW_CHARS = 400


class RetrievalDebugService:
    def __init__(
        self,
        db: Session,
        *,
        retriever: HybridRiskKnowledgeRetriever | None = None,
        text_preview_chars: int = _DEFAULT_TEXT_PREVIEW_CHARS,
    ) -> None:
        self._db = db
        self._retriever = retriever
        self._text_preview_chars = max(1, text_preview_chars)

    def debug_retrieve(self, request: DebugRetrieveRequest) -> DebugRetrieveResponse:
        started = perf_counter()
        retriever = self._retriever or HybridRiskKnowledgeRetriever(db=self._db)
        result = retriever.retrieve(
            RetrievalQuery(
                kb_id=request.kb_id,
                query=request.query,
                document_id=request.document_id,
                version_id=request.version_id,
                fused_top_k=request.top_k,
                vector_top_k=max(request.top_k, 10),
                keyword_top_k=max(request.top_k, 10),
            )
        )
        latency_ms = int((perf_counter() - started) * 1000)
        candidates = [
            DebugRetrieveCandidateResponse(
                rank=item.fused_rank,
                document_id=item.document_id,
                version_id=item.version_id,
                chunk_id=item.chunk_id,
                manifest_index_id=item.manifest_index_id,
                section_path=" / ".join(item.section_path) if item.section_path else None,
                page_start=item.page_start,
                page_end=item.page_end,
                content_hash=item.content_hash,
                text_preview=self._truncate(item.text),
                scores=DebugRetrieveCandidateScoresResponse(
                    vector_score=item.vector_raw_score,
                    bm25_score=item.keyword_score,
                    rrf_score=item.fused_score,
                ),
            )
            for item in result.candidates[: request.top_k]
        ]
        return DebugRetrieveResponse(
            query=request.query,
            kb_id=request.kb_id,
            scope=DebugRetrieveScopeResponse(
                scope_type=result.scope_type.value,
                document_id=result.document_id,
                version_id=result.version_id,
                active_manifest_index_ids=list(result.active_manifest_index_ids),
            ),
            candidates=candidates,
            diagnostics=DebugRetrieveDiagnosticsResponse(
                candidate_count=len(candidates),
                fusion_method="rrf",
                latency_ms=latency_ms,
                vector_hit_count=self._optional_int(result.diagnostics.get("vector_hit_count")),
                keyword_hit_count=self._optional_int(result.diagnostics.get("keyword_hit_count")),
                fused_hit_count=self._optional_int(result.diagnostics.get("fused_hit_count")),
            ),
        )

    def _truncate(self, text: str) -> str:
        normalized = text.strip()
        if len(normalized) <= self._text_preview_chars:
            return normalized
        return normalized[: self._text_preview_chars].rstrip() + "..."

    @staticmethod
    def _optional_int(value) -> int | None:
        if value is None:
            return None
        return int(value)
