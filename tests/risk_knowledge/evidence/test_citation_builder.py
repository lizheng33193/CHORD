from __future__ import annotations


def test_citation_builder_generates_stable_id_across_rank_changes() -> None:
    from app.risk_knowledge.evidence.citation_builder import CitationBuilder
    from app.risk_knowledge.evidence.schemas import SelectedEvidence

    builder = CitationBuilder()
    base_evidence = SelectedEvidence(
        evidence_id="ev_risk_guide_v1_chunk_000001",
        candidate_id="cand_001",
        chunk_id="risk_guide_v1_chunk_000001",
        document_id="risk_guide",
        version_id="risk_guide_v1",
        manifest_index_id="idx_risk_guide",
        content_hash="sha256:c1",
        text="loan risk warning signal",
        section_path=["risk_guide", "section-1"],
        page_start=1,
        page_end=1,
        retrieval_fused_score=0.7,
        retrieval_fused_rank=1,
        rerank_score=0.9,
        rerank_rank=1,
        selected_rank=1,
        matched_channels=["vector", "keyword"],
    )

    citations_a = builder.build([base_evidence])
    citations_b = builder.build([base_evidence.model_copy(update={"selected_rank": 5, "rerank_rank": 8})])

    assert citations_a[0].citation_id == citations_b[0].citation_id
    assert citations_a[0].chunk_id == base_evidence.chunk_id
    assert citations_a[0].content_hash == base_evidence.content_hash
