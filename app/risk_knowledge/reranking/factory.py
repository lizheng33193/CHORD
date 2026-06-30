"""Provider selection helpers for M2D-11 reranking."""

from __future__ import annotations

from app.core.config import settings
from app.risk_knowledge.reranking.dashscope_provider import DashScopeRerankerProvider
from app.risk_knowledge.reranking.deterministic_provider import DeterministicRerankerProvider
from app.risk_knowledge.reranking.errors import RerankerProviderConfigError


def build_reranker_provider_from_settings():
    provider_name = settings.risk_knowledge_reranker_provider.strip().lower()
    if provider_name == "deterministic":
        return DeterministicRerankerProvider()
    if provider_name == "dashscope":
        return DashScopeRerankerProvider(
            api_key=settings.dashscope_api_key,
            model=settings.risk_knowledge_reranker_model,
            endpoint=settings.risk_knowledge_reranker_http_base_url,
            timeout_seconds=settings.risk_knowledge_reranker_timeout_seconds,
        )
    raise RerankerProviderConfigError(f"unsupported reranker provider: {settings.risk_knowledge_reranker_provider}")
