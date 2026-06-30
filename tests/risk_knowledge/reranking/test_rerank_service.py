from __future__ import annotations

import pytest

from app.risk_knowledge.retrieval.schemas import (
    HybridRetrievalCandidate,
    HybridRetrievalResult,
    RetrievalScopeType,
)


class _DuplicateCandidateProvider:
    provider_name = "duplicate-provider"

    def rerank(self, request):
        from app.risk_knowledge.reranking.schemas import RerankItem, RerankResult

        first_candidate = request.candidates[0]
        return RerankResult(
            provider=self.provider_name,
            model=request.model,
            items=[
                RerankItem(
                    candidate_id=first_candidate.candidate_id,
                    chunk_id=first_candidate.chunk_id,
                    rerank_score=0.9,
                    rerank_rank=99,
                ),
                RerankItem(
                    candidate_id=first_candidate.candidate_id,
                    chunk_id=first_candidate.chunk_id,
                    rerank_score=0.8,
                    rerank_rank=100,
                ),
            ],
        )


class _UnknownCandidateProvider:
    provider_name = "unknown-provider"

    def rerank(self, request):
        from app.risk_knowledge.reranking.schemas import RerankItem, RerankResult

        return RerankResult(
            provider=self.provider_name,
            model=request.model,
            items=[
                RerankItem(
                    candidate_id="cand_unknown",
                    chunk_id=request.candidates[0].chunk_id,
                    rerank_score=0.7,
                    rerank_rank=2,
                )
            ],
        )


class _IndexOnlyProvider:
    provider_name = "index-only-provider"

    def rerank(self, request):
        from app.risk_knowledge.reranking.schemas import RerankItem, RerankResult

        second = request.candidates[1]
        first = request.candidates[0]
        return RerankResult(
            provider=self.provider_name,
            model=request.model,
            items=[
                RerankItem(
                    candidate_index=1,
                    candidate_id=second.candidate_id,
                    chunk_id=second.chunk_id,
                    rerank_score=0.9,
                    rerank_rank=42,
                ),
                RerankItem(
                    candidate_index=0,
                    candidate_id=first.candidate_id,
                    chunk_id=first.chunk_id,
                    rerank_score=0.4,
                    rerank_rank=77,
                ),
            ],
        )


def _build_candidate(*, chunk_id: str, doc_id: str, rank: int, text: str, content_hash: str) -> HybridRetrievalCandidate:
    return HybridRetrievalCandidate(
        retrieval_key=f"idx_{doc_id}:{chunk_id}",
        chunk_id=chunk_id,
        document_id=doc_id,
        version_id=f"{doc_id}_v1",
        manifest_index_id=f"idx_{doc_id}",
        content_hash=content_hash,
        section_path=[doc_id, f"section-{rank}"],
        page_start=rank,
        page_end=rank,
        text=text,
        vector_raw_score=0.1 * rank,
        keyword_score=0.2 * rank,
        vector_rank=rank,
        keyword_rank=rank,
        fused_score=0.3 * rank,
        fused_rank=rank,
        matched_channels=["vector", "keyword"],
    )


def _build_retrieval_result(candidates: list[HybridRetrievalCandidate]) -> HybridRetrievalResult:
    return HybridRetrievalResult(
        query="loan risk",
        normalized_query="loan risk",
        kb_id="risk_domain_knowledge",
        scope_type=RetrievalScopeType.KB_ACTIVE_DOCUMENTS,
        document_id=None,
        version_id=None,
        active_manifest_index_ids=["idx_risk_guide"],
        embedding_provider="deterministic_test",
        embedding_model="deterministic-v1",
        embedding_dimension=2,
        candidates=candidates,
        diagnostics={"vector_hit_count": len(candidates)},
    )


def test_rerank_service_generates_stable_candidate_ids_and_rebuilds_rank() -> None:
    from app.risk_knowledge.reranking.deterministic_provider import DeterministicRerankerProvider
    from app.risk_knowledge.reranking.rerank_service import RerankService

    retrieval_result = _build_retrieval_result(
        [
            _build_candidate(
                chunk_id="risk_guide_v1_chunk_000001",
                doc_id="risk_guide",
                rank=1,
                text="loan risk warning signal",
                content_hash="sha256:c1",
            ),
            _build_candidate(
                chunk_id="risk_guide_v1_chunk_000002",
                doc_id="risk_guide",
                rank=2,
                text="post-loan monitoring and collection strategy",
                content_hash="sha256:c2",
            ),
        ]
    )

    result = RerankService(
        provider=DeterministicRerankerProvider(),
        model="deterministic-rerank-v1",
        top_n=10,
    ).rerank_retrieval_result(retrieval_result)

    assert [item.rerank_rank for item in result.items] == [1, 2]
    assert result.items[0].candidate_index == 1
    assert result.items[0].candidate_id.startswith("cand_")
    assert result.items[0].candidate_id != result.items[1].candidate_id
    assert result.items[0].chunk_id == "risk_guide_v1_chunk_000002"


def test_rerank_service_rejects_unknown_candidate_id() -> None:
    from app.risk_knowledge.reranking.errors import RerankerResultMismatchError
    from app.risk_knowledge.reranking.rerank_service import RerankService

    retrieval_result = _build_retrieval_result(
        [
            _build_candidate(
                chunk_id="risk_guide_v1_chunk_000001",
                doc_id="risk_guide",
                rank=1,
                text="loan risk warning signal",
                content_hash="sha256:c1",
            )
        ]
    )

    with pytest.raises(RerankerResultMismatchError):
        RerankService(
            provider=_UnknownCandidateProvider(),
            model="deterministic-rerank-v1",
            top_n=5,
        ).rerank_retrieval_result(retrieval_result)


def test_rerank_service_rejects_duplicate_candidate_id() -> None:
    from app.risk_knowledge.reranking.errors import RerankerResultMismatchError
    from app.risk_knowledge.reranking.rerank_service import RerankService

    retrieval_result = _build_retrieval_result(
        [
            _build_candidate(
                chunk_id="risk_guide_v1_chunk_000001",
                doc_id="risk_guide",
                rank=1,
                text="loan risk warning signal",
                content_hash="sha256:c1",
            ),
            _build_candidate(
                chunk_id="risk_guide_v1_chunk_000002",
                doc_id="risk_guide",
                rank=2,
                text="post-loan monitoring and collection strategy",
                content_hash="sha256:c2",
            ),
        ]
    )

    with pytest.raises(RerankerResultMismatchError):
        RerankService(
            provider=_DuplicateCandidateProvider(),
            model="deterministic-rerank-v1",
            top_n=5,
        ).rerank_retrieval_result(retrieval_result)


def test_rerank_service_maps_index_results_and_clamps_top_n() -> None:
    from app.risk_knowledge.reranking.rerank_service import RerankService

    retrieval_result = _build_retrieval_result(
        [
            _build_candidate(
                chunk_id="risk_guide_v1_chunk_000001",
                doc_id="risk_guide",
                rank=1,
                text="loan risk warning signal",
                content_hash="sha256:c1",
            ),
            _build_candidate(
                chunk_id="risk_guide_v1_chunk_000002",
                doc_id="risk_guide",
                rank=2,
                text="post-loan monitoring and collection strategy",
                content_hash="sha256:c2",
            ),
        ]
    )

    result = RerankService(
        provider=_IndexOnlyProvider(),
        model="index-rerank-v1",
        top_n=99,
    ).rerank_retrieval_result(retrieval_result)

    assert len(result.items) == 2
    assert [item.candidate_index for item in result.items] == [1, 0]
    assert [item.rerank_rank for item in result.items] == [1, 2]
