from __future__ import annotations


def test_rrf_overlap_candidate_scores_higher() -> None:
    from app.risk_knowledge.retrieval.rrf import RrfFusionService
    from app.risk_knowledge.retrieval.schemas import KeywordRetrievalHit, VectorRetrievalHit

    vector_hits = [
        VectorRetrievalHit(
            retrieval_key="idx1:chunk1",
            chunk_id="chunk1",
            document_id="doc1",
            version_id="v1",
            manifest_index_id="idx1",
            vector_id=0,
            raw_score=0.1,
            distance_metric="l2",
            rank=1,
        ),
    ]
    keyword_hits = [
        KeywordRetrievalHit(
            retrieval_key="idx1:chunk1",
            chunk_id="chunk1",
            document_id="doc1",
            version_id="v1",
            manifest_index_id="idx1",
            score=1.2,
            rank=1,
            matched_terms=["loan"],
        ),
        KeywordRetrievalHit(
            retrieval_key="idx1:chunk2",
            chunk_id="chunk2",
            document_id="doc1",
            version_id="v1",
            manifest_index_id="idx1",
            score=1.0,
            rank=2,
            matched_terms=["loan"],
        ),
    ]

    fused = RrfFusionService(rrf_k=60).fuse(vector_hits, keyword_hits, fused_top_k=2)

    assert fused[0].retrieval_key == "idx1:chunk1"
    assert fused[0].matched_channels == ["vector", "keyword"]
