"""Rerank service that adapts retrieval candidates and validates provider output."""

from __future__ import annotations

import hashlib

from app.risk_knowledge.retrieval.schemas import HybridRetrievalResult
from app.risk_knowledge.reranking.errors import (
    InvalidRerankRequestError,
    RerankerResultMismatchError,
)
from app.risk_knowledge.reranking.provider import RerankerProvider
from app.risk_knowledge.reranking.schemas import (
    RerankCandidateInput,
    RerankItem,
    RerankRequest,
    RerankResult,
)


def build_candidate_id(
    *,
    manifest_index_id: str,
    document_id: str,
    version_id: str,
    chunk_id: str,
    content_hash: str,
) -> str:
    payload = "::".join([manifest_index_id, document_id, version_id, chunk_id, content_hash])
    return f"cand_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


class RerankService:
    def __init__(
        self,
        *,
        provider: RerankerProvider,
        model: str,
        top_n: int | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._top_n = top_n

    def rerank_retrieval_result(self, retrieval_result: HybridRetrievalResult) -> RerankResult:
        request = self._build_request(retrieval_result)
        raw_result = self._provider.rerank(request)
        return self._normalize_result(raw_result, request)

    def _build_request(self, retrieval_result: HybridRetrievalResult) -> RerankRequest:
        if not retrieval_result.candidates:
            raise InvalidRerankRequestError("retrieval_result.candidates must not be empty")

        candidates = [
            RerankCandidateInput(
                candidate_id=build_candidate_id(
                    manifest_index_id=candidate.manifest_index_id,
                    document_id=candidate.document_id,
                    version_id=candidate.version_id,
                    chunk_id=candidate.chunk_id,
                    content_hash=candidate.content_hash,
                ),
                chunk_id=candidate.chunk_id,
                document_id=candidate.document_id,
                version_id=candidate.version_id,
                manifest_index_id=candidate.manifest_index_id,
                content_hash=candidate.content_hash,
                text=candidate.text,
                section_path=" / ".join(candidate.section_path) if candidate.section_path else None,
                page_start=candidate.page_start,
                page_end=candidate.page_end,
                retrieval_fused_score=candidate.fused_score,
                retrieval_fused_rank=candidate.fused_rank,
            )
            for candidate in retrieval_result.candidates
        ]
        top_n = None if self._top_n is None else min(self._top_n, len(candidates))
        return RerankRequest(
            query=retrieval_result.normalized_query,
            candidates=candidates,
            model=self._model,
            top_n=top_n,
        )

    def _normalize_result(self, result: RerankResult, request: RerankRequest) -> RerankResult:
        by_id = {candidate.candidate_id: candidate for candidate in request.candidates}
        used_candidate_ids: set[str] = set()
        normalized_items: list[RerankItem] = []

        for rank, item in enumerate(result.items, start=1):
            candidate_id = item.candidate_id
            if candidate_id is None:
                if item.candidate_index is None or item.candidate_index >= len(request.candidates):
                    raise RerankerResultMismatchError("provider returned candidate without a valid index or id")
                candidate_id = request.candidates[item.candidate_index].candidate_id
            if candidate_id not in by_id:
                raise RerankerResultMismatchError(f"unknown candidate_id returned by provider: {candidate_id}")
            if candidate_id in used_candidate_ids:
                raise RerankerResultMismatchError(f"duplicate candidate_id returned by provider: {candidate_id}")
            if item.chunk_id != by_id[candidate_id].chunk_id:
                raise RerankerResultMismatchError(f"chunk_id mismatch for candidate_id={candidate_id}")
            used_candidate_ids.add(candidate_id)
            normalized_items.append(
                RerankItem(
                    candidate_index=request.candidates.index(by_id[candidate_id]),
                    candidate_id=candidate_id,
                    chunk_id=item.chunk_id,
                    rerank_score=float(item.rerank_score),
                    rerank_rank=rank,
                )
            )

        return RerankResult(provider=result.provider, model=result.model, items=normalized_items)
