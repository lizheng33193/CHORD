from __future__ import annotations

from tests.risk_knowledge.embedding.real_provider_smoke import require_real_embedding_provider_smoke
from tests.risk_knowledge.retrieval.conftest import DeterministicRetrievalEmbeddingProvider


def test_query_embedding_service_uses_query_input_type() -> None:
    from app.risk_knowledge.retrieval.query_embedding import QueryEmbeddingService

    provider = DeterministicRetrievalEmbeddingProvider(dimension=2)
    result = QueryEmbeddingService(provider=provider, expected_dimension=2).embed_query("loan warning")

    assert result.dimension == 2
    assert len(result.vector) == 2


def test_real_query_embedding_smoke() -> None:
    require_real_embedding_provider_smoke()

    from app.core.config import settings
    from app.risk_knowledge.embedding.factory import build_embedding_provider_from_settings
    from app.risk_knowledge.retrieval.query_embedding import QueryEmbeddingService

    provider = build_embedding_provider_from_settings()
    result = QueryEmbeddingService(
        provider=provider,
        expected_dimension=settings.risk_knowledge_embedding_dimension,
    ).embed_query("loan risk warning")

    assert provider.provider_name == settings.risk_knowledge_embedding_provider
    assert result.model == settings.risk_knowledge_embedding_model
    assert result.dimension == settings.risk_knowledge_embedding_dimension
    assert len(result.vector) == settings.risk_knowledge_embedding_dimension
