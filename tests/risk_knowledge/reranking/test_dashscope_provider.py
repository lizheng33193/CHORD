from __future__ import annotations

import pytest

from app.risk_knowledge.reranking.schemas import RerankCandidateInput, RerankRequest


def _build_request() -> RerankRequest:
    return RerankRequest(
        query="loan risk",
        model="qwen3-rerank",
        candidates=[
            RerankCandidateInput(
                candidate_id="cand_001",
                chunk_id="risk_guide_v1_chunk_000001",
                document_id="risk_guide",
                version_id="risk_guide_v1",
                manifest_index_id="idx_risk_guide",
                content_hash="sha256:c1",
                text="loan risk warning signal",
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
                text="post-loan monitoring and collection strategy",
                section_path="risk_guide / section-2",
                page_start=2,
                page_end=2,
                retrieval_fused_score=0.6,
                retrieval_fused_rank=2,
            ),
        ],
    )


def test_dashscope_provider_requires_api_key() -> None:
    from app.risk_knowledge.reranking.dashscope_provider import DashScopeRerankerProvider
    from app.risk_knowledge.reranking.errors import RerankerProviderConfigError

    provider = DashScopeRerankerProvider(api_key=None, endpoint="https://example.invalid")

    with pytest.raises(RerankerProviderConfigError):
        provider.rerank(_build_request())


def test_dashscope_provider_redacts_api_key_from_errors(monkeypatch) -> None:
    from app.risk_knowledge.reranking.dashscope_provider import DashScopeRerankerProvider
    from app.risk_knowledge.reranking.errors import RerankerProviderError

    provider = DashScopeRerankerProvider(api_key="secret-key", endpoint="https://example.invalid")

    def _boom(_payload):
        raise RuntimeError("bad request secret-key")

    monkeypatch.setattr(provider, "_post_rerank_request", _boom)

    with pytest.raises(RerankerProviderError) as exc_info:
        provider.rerank(_build_request())

    assert "secret-key" not in str(exc_info.value)
    assert "[redacted]" in str(exc_info.value)


def test_dashscope_provider_maps_results_without_leaking_transport_shape(monkeypatch) -> None:
    from app.risk_knowledge.reranking.dashscope_provider import DashScopeRerankerProvider

    provider = DashScopeRerankerProvider(api_key="secret-key", endpoint="https://example.invalid")

    monkeypatch.setattr(
        provider,
        "_post_rerank_request",
        lambda _payload: {
            "output": {
                "results": [
                    {"index": 1, "relevance_score": 0.88},
                    {"index": 0, "relevance_score": 0.42},
                ]
            }
        },
    )

    result = provider.rerank(_build_request())

    assert result.provider == "dashscope"
    assert result.model == "qwen3-rerank"
    assert [item.candidate_index for item in result.items] == [1, 0]
    assert [item.chunk_id for item in result.items] == [
        "risk_guide_v1_chunk_000002",
        "risk_guide_v1_chunk_000001",
    ]
