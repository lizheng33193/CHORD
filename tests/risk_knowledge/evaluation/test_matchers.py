from __future__ import annotations

from app.risk_knowledge.retrieval.schemas import HybridRetrievalCandidate


def test_expected_evidence_matcher_prefers_chunk_id() -> None:
    from app.risk_knowledge.evaluation.matchers import expected_evidence_matches_candidate
    from app.risk_knowledge.evaluation.schemas import ExpectedEvidence

    candidate = HybridRetrievalCandidate(
        retrieval_key="idx:risk_chunk_001",
        chunk_id="risk_chunk_001",
        document_id="risk_guide",
        version_id="risk_guide_v1",
        manifest_index_id="idx_risk_guide",
        content_hash="sha256:risk-1",
        section_path=["风险手册", "多头借贷"],
        page_start=1,
        page_end=1,
        text="多个平台重复申请借款通常意味着更高信用风险。",
        vector_raw_score=0.1,
        keyword_score=0.9,
        vector_rank=1,
        keyword_rank=1,
        fused_score=0.95,
        fused_rank=1,
        matched_channels=["vector", "keyword"],
    )

    expected = ExpectedEvidence(
        chunk_id="risk_chunk_001",
        text_contains=["不会被走到"],
    )

    assert expected_evidence_matches_candidate(expected, candidate) is True


def test_expected_evidence_matcher_falls_back_to_text_contains() -> None:
    from app.risk_knowledge.evaluation.matchers import expected_evidence_matches_candidate
    from app.risk_knowledge.evaluation.schemas import ExpectedEvidence

    candidate = HybridRetrievalCandidate(
        retrieval_key="idx:risk_chunk_001",
        chunk_id="risk_chunk_001",
        document_id="risk_guide",
        version_id="risk_guide_v1",
        manifest_index_id="idx_risk_guide",
        content_hash="sha256:risk-1",
        section_path=["风险手册", "多头借贷"],
        page_start=1,
        page_end=1,
        text="多个平台重复申请借款通常意味着更高信用风险。",
        vector_raw_score=0.1,
        keyword_score=0.9,
        vector_rank=1,
        keyword_rank=1,
        fused_score=0.95,
        fused_rank=1,
        matched_channels=["vector", "keyword"],
    )

    expected = ExpectedEvidence(
        section_path_contains="不存在的章节",
        text_contains=["多个平台", "信用风险"],
    )

    assert expected_evidence_matches_candidate(expected, candidate) is True
