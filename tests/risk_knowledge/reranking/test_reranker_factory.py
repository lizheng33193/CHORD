from __future__ import annotations


def test_reranker_factory_builds_dashscope_provider(monkeypatch) -> None:
    from app.core.config import settings
    from app.risk_knowledge.reranking.dashscope_provider import DashScopeRerankerProvider
    from app.risk_knowledge.reranking.factory import build_reranker_provider_from_settings

    monkeypatch.setattr(settings, "risk_knowledge_reranker_provider", "dashscope", raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_reranker_model", "qwen3-rerank", raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_reranker_http_base_url", "https://example.invalid", raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_reranker_timeout_seconds", 15, raising=False)
    monkeypatch.setattr(settings, "dashscope_api_key", "test-key", raising=False)

    provider = build_reranker_provider_from_settings()

    assert isinstance(provider, DashScopeRerankerProvider)
    assert provider.model == "qwen3-rerank"
    assert provider.timeout_seconds == 15


def test_reranker_factory_builds_deterministic_provider(monkeypatch) -> None:
    from app.core.config import settings
    from app.risk_knowledge.reranking.deterministic_provider import DeterministicRerankerProvider
    from app.risk_knowledge.reranking.factory import build_reranker_provider_from_settings

    monkeypatch.setattr(settings, "risk_knowledge_reranker_provider", "deterministic", raising=False)

    provider = build_reranker_provider_from_settings()

    assert isinstance(provider, DeterministicRerankerProvider)
