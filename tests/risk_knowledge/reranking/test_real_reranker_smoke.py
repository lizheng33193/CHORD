from __future__ import annotations

import os

import pytest

from app.risk_knowledge.reranking.schemas import RerankCandidateInput, RerankRequest


def _require_real_reranker_smoke() -> None:
    if os.getenv("CHORD_RUN_REAL_RERANKER_TESTS") != "1":
        pytest.skip("set CHORD_RUN_REAL_RERANKER_TESTS=1 to run real reranker smoke")
    if not os.getenv("DASHSCOPE_API_KEY"):
        pytest.skip("set DASHSCOPE_API_KEY to run DashScope reranker smoke")
    if os.getenv("RISK_KNOWLEDGE_RERANKER_PROVIDER", "dashscope") != "dashscope":
        pytest.skip("set RISK_KNOWLEDGE_RERANKER_PROVIDER=dashscope to run DashScope reranker smoke")


def test_dashscope_reranker_real_smoke() -> None:
    _require_real_reranker_smoke()

    from app.core.config import settings
    from app.risk_knowledge.reranking.dashscope_provider import DashScopeRerankerProvider

    provider = DashScopeRerankerProvider(
        api_key=settings.dashscope_api_key,
        model=settings.risk_knowledge_reranker_model,
        endpoint=settings.risk_knowledge_reranker_http_base_url,
        timeout_seconds=settings.risk_knowledge_reranker_timeout_seconds,
    )
    result = provider.rerank(
        RerankRequest(
            query="什么是多头借贷风险？",
            model=settings.risk_knowledge_reranker_model,
            top_n=2,
            candidates=[
                RerankCandidateInput(
                    candidate_id="cand_001",
                    chunk_id="risk_guide_v1_chunk_000001",
                    document_id="risk_guide",
                    version_id="risk_guide_v1",
                    manifest_index_id="idx_risk_guide",
                    content_hash="sha256:c1",
                    text="多头借贷是指用户在多个平台频繁申请或使用信贷产品，可能反映资金压力和信用风险。",
                    section_path="risk_guide / section-1",
                    page_start=1,
                    page_end=1,
                    retrieval_fused_score=0.8,
                    retrieval_fused_rank=1,
                ),
                RerankCandidateInput(
                    candidate_id="cand_002",
                    chunk_id="risk_guide_v1_chunk_000002",
                    document_id="risk_guide",
                    version_id="risk_guide_v1",
                    manifest_index_id="idx_risk_guide",
                    content_hash="sha256:c2",
                    text="天气晴朗适合户外运动。",
                    section_path="risk_guide / section-2",
                    page_start=2,
                    page_end=2,
                    retrieval_fused_score=0.5,
                    retrieval_fused_rank=2,
                ),
            ],
        )
    )

    assert result.provider == "dashscope"
    assert result.model == settings.risk_knowledge_reranker_model
    assert len(result.items) >= 1
    assert all(item.rerank_rank >= 1 for item in result.items)
    assert all(isinstance(item.rerank_score, float) for item in result.items)
