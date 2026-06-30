from __future__ import annotations

from app.risk_knowledge.retrieval.schemas import (
    HybridRetrievalCandidate,
    HybridRetrievalResult,
    RetrievalScopeType,
)
from app.risk_knowledge.reranking.schemas import RerankItem, RerankResult


class _ProviderMustNotBeCalled:
    provider_name = "must-not-be-called"

    def rerank(self, request):  # pragma: no cover - this path should not execute
        raise AssertionError("rerank provider should not be called for empty retrieval candidates")


class _FixedProvider:
    provider_name = "fixed-provider"

    def rerank(self, request):
        return RerankResult(
            provider=self.provider_name,
            model=request.model,
            items=[
                RerankItem(
                    candidate_id=request.candidates[0].candidate_id,
                    chunk_id=request.candidates[0].chunk_id,
                    rerank_score=0.1,
                    rerank_rank=10,
                )
            ],
        )


def _build_candidate() -> HybridRetrievalCandidate:
    return HybridRetrievalCandidate(
        retrieval_key="idx_risk_guide:risk_guide_v1_chunk_000001",
        chunk_id="risk_guide_v1_chunk_000001",
        document_id="risk_guide",
        version_id="risk_guide_v1",
        manifest_index_id="idx_risk_guide",
        content_hash="sha256:c1",
        section_path=["risk_guide", "section-1"],
        page_start=1,
        page_end=1,
        text="loan risk warning signal",
        vector_raw_score=0.5,
        keyword_score=0.6,
        vector_rank=1,
        keyword_rank=1,
        fused_score=0.7,
        fused_rank=1,
        matched_channels=["vector", "keyword"],
    )


def test_bundle_builder_returns_no_candidates_without_calling_provider() -> None:
    from app.risk_knowledge.evidence.evidence_bundle_builder import RiskEvidenceBundleBuilder

    retrieval_result = HybridRetrievalResult(
        query="loan risk",
        normalized_query="loan risk",
        kb_id="risk_domain_knowledge",
        scope_type=RetrievalScopeType.KB_ACTIVE_DOCUMENTS,
        active_manifest_index_ids=[],
        embedding_provider="deterministic_test",
        embedding_model="deterministic-v1",
        embedding_dimension=2,
        candidates=[],
        diagnostics={},
    )

    bundle = RiskEvidenceBundleBuilder.from_provider(
        provider=_ProviderMustNotBeCalled(),
        rerank_model="deterministic-rerank-v1",
    ).build(retrieval_result)

    assert bundle.should_answer is False
    assert bundle.refusal_reason == "no_candidates"
    assert bundle.selected_evidence == []
    assert bundle.citations == []


def test_bundle_builder_preserves_citations_when_gate_fails() -> None:
    from app.risk_knowledge.evidence.evidence_bundle_builder import RiskEvidenceBundleBuilder

    retrieval_result = HybridRetrievalResult(
        query="loan risk",
        normalized_query="loan risk",
        kb_id="risk_domain_knowledge",
        scope_type=RetrievalScopeType.KB_ACTIVE_DOCUMENTS,
        active_manifest_index_ids=["idx_risk_guide"],
        embedding_provider="deterministic_test",
        embedding_model="deterministic-v1",
        embedding_dimension=2,
        candidates=[_build_candidate()],
        diagnostics={},
    )

    bundle = RiskEvidenceBundleBuilder.from_provider(
        provider=_FixedProvider(),
        rerank_model="fixed-rerank-v1",
        min_rerank_score=0.05,
        min_evidence_count=2,
    ).build(retrieval_result)

    assert bundle.should_answer is False
    assert bundle.refusal_reason == "below_min_evidence_count"
    assert len(bundle.selected_evidence) == 1
    assert len(bundle.citations) == 1
    assert bundle.citations[0].chunk_id == bundle.selected_evidence[0].chunk_id
    assert "answer" not in bundle.model_dump()
    assert "generated_text" not in bundle.model_dump()
