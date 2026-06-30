"""Provider selection helpers for M2D embedding runtime."""

from __future__ import annotations

from app.core.config import settings
from app.risk_knowledge.embedding.dashscope_provider import DashScopeEmbeddingProvider
from app.risk_knowledge.embedding.errors import EmbeddingProviderUnavailableError
from app.risk_knowledge.embedding.openai_compatible_provider import OpenAICompatibleEmbeddingProvider


def build_embedding_provider_from_settings():
    provider_name = settings.risk_knowledge_embedding_provider.strip().lower()
    if provider_name == "openai_compatible":
        return OpenAICompatibleEmbeddingProvider(
            api_key=settings.risk_knowledge_embedding_api_key,
            base_url=settings.risk_knowledge_embedding_base_url,
            model=settings.risk_knowledge_embedding_model,
            dimension=settings.risk_knowledge_embedding_dimension,
            max_batch_size=settings.risk_knowledge_embedding_max_batch_size,
        )
    if provider_name == "dashscope":
        return DashScopeEmbeddingProvider(
            api_key=settings.dashscope_api_key,
            model=settings.risk_knowledge_embedding_model,
            dimension=settings.risk_knowledge_embedding_dimension,
            output_type=settings.risk_knowledge_embedding_output_type,
            text_type=settings.risk_knowledge_embedding_text_type,
            endpoint=settings.risk_knowledge_embedding_base_url,
        )
    raise EmbeddingProviderUnavailableError(f"unsupported embedding provider: {settings.risk_knowledge_embedding_provider}")
