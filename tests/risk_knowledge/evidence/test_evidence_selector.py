from __future__ import annotations

from app.risk_knowledge.retrieval.schemas import (
    HybridRetrievalCandidate,
    HybridRetrievalResult,
    RetrievalScopeType,
)
from app.risk_knowledge.reranking.schemas import RerankItem, RerankResult


def _build_candidate(*, chunk_id: str, content_hash: str, text: str, rank: int) -> HybridRetrievalCandidate:
    return HybridRetrievalCandidate(
        retrieval_key=f"idx_risk_guide:{chunk_id}",
        chunk_id=chunk_id,
        document_id="risk_guide",
        version_id="risk_guide_v1",
        manifest_index_id="idx_risk_guide",
        content_hash=content_hash,
        section_path=["risk_guide", f"section-{rank}"],
        page_start=rank,
        page_end=rank,
        text=text,
        vector_raw_score=0.1 * rank,
        keyword_score=0.2 * rank,
        vector_rank=rank,
        keyword_rank=rank,
        fused_score=1.0 / rank,
        fused_rank=rank,
        matched_channels=["vector", "keyword"],
    )


def _build_retrieval_result(candidates: list[HybridRetrievalCandidate]) -> HybridRetrievalResult:
    return HybridRetrievalResult(
        query="loan risk",
        normalized_query="loan risk",
        kb_id="risk_domain_knowledge",
        scope_type=RetrievalScopeType.KB_ACTIVE_DOCUMENTS,
        active_manifest_index_ids=["idx_risk_guide"],
        embedding_provider="deterministic_test",
        embedding_model="deterministic-v1",
        embedding_dimension=2,
        candidates=candidates,
        diagnostics={},
    )


def test_evidence_selector_dedups_and_skips_by_total_chars() -> None:
    from app.risk_knowledge.evidence.evidence_selector import EvidenceSelector
    from app.risk_knowledge.evidence.schemas import EvidenceSelectionConfig
    from app.risk_knowledge.reranking.rerank_service import build_candidate_id

    candidates = [
        _build_candidate(
            chunk_id="risk_guide_v1_chunk_000001",
            content_hash="sha256:dup",
            text="alpha",
            rank=1,
        ),
        _build_candidate(
            chunk_id="risk_guide_v1_chunk_000002",
            content_hash="sha256:dup",
            text="alpha",
            rank=2,
        ),
        _build_candidate(
            chunk_id="risk_guide_v1_chunk_000003",
            content_hash="sha256:unique",
            text="this text is too long to fit",
            rank=3,
        ),
        _build_candidate(
            chunk_id="risk_guide_v1_chunk_000004",
            content_hash="sha256:small",
            text="tiny",
            rank=4,
        ),
    ]
    retrieval_result = _build_retrieval_result(candidates)
    rerank_result = RerankResult(
        provider="deterministic",
        model="deterministic-rerank-v1",
        items=[
            RerankItem(
                candidate_id=build_candidate_id(
                    manifest_index_id=item.manifest_index_id,
                    document_id=item.document_id,
                    version_id=item.version_id,
                    chunk_id=item.chunk_id,
                    content_hash=item.content_hash,
                ),
                chunk_id=item.chunk_id,
                rerank_score=0.9 - index * 0.1,
                rerank_rank=index + 1,
            )
            for index, item in enumerate(candidates)
        ],
    )

    result = EvidenceSelector().select(
        retrieval_result=retrieval_result,
        rerank_result=rerank_result,
        config=EvidenceSelectionConfig(
            max_evidence_count=5,
            min_evidence_count=1,
            min_rerank_score=0.1,
            max_total_chars=10,
            dedup_by_content_hash=True,
        ),
    )

    assert [item.chunk_id for item in result.selected_evidence] == [
        "risk_guide_v1_chunk_000001",
        "risk_guide_v1_chunk_000004",
    ]
    assert result.diagnostics["skipped_by_duplicate"] == 1
    assert result.diagnostics["skipped_by_total_chars"] == 1
    assert result.diagnostics["selected_total_chars"] == 9
