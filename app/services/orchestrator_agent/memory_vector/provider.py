"""Embedding providers for M6A memory vector shadow indexing."""

from __future__ import annotations

import hashlib
from typing import Protocol, runtime_checkable

from app.core.config import settings
from app.risk_knowledge.embedding.dashscope_provider import DashScopeEmbeddingProvider
from app.risk_knowledge.embedding.openai_compatible_provider import (
    OpenAICompatibleEmbeddingProvider,
)
from app.risk_knowledge.embedding.schemas import EmbeddingInput


@runtime_checkable
class MemoryEmbeddingProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed_texts(self, texts: list[str], *, input_type: str = "document") -> list[list[float]]: ...


class DeterministicMemoryEmbeddingProvider:
    provider_name = "deterministic"

    def __init__(self, *, dimension: int, model_name: str = "memory-fake-embedding-v1") -> None:
        self._dimension = max(1, int(dimension))
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_texts(self, texts: list[str], *, input_type: str = "document") -> list[list[float]]:
        del input_type
        vectors: list[list[float]] = []
        for text in texts:
            seed = hashlib.sha256(str(text).encode("utf-8")).digest()
            floats: list[float] = []
            source = seed
            while len(floats) < self._dimension:
                for idx in range(0, len(source), 4):
                    chunk = source[idx : idx + 4]
                    if len(chunk) < 4:
                        continue
                    floats.append(int.from_bytes(chunk, "big") / 2**32)
                    if len(floats) >= self._dimension:
                        break
                source = hashlib.sha256(source).digest()
            vectors.append(floats[: self._dimension])
        return vectors


class RiskKnowledgeProviderAdapter:
    def __init__(self, *, provider: object, provider_name: str, model_name: str, dimension: int) -> None:
        self._provider = provider
        self._provider_name = provider_name
        self._model_name = model_name
        self._dimension = dimension

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_texts(self, texts: list[str], *, input_type: str = "document") -> list[list[float]]:
        records = self._provider.embed(
            [
                EmbeddingInput(
                    chunk_id=f"memory_vector_{index}",
                    content_hash=f"sha256:memory-vector:{index}",
                    text=text,
                    input_type="query" if input_type == "query" else "document",
                )
                for index, text in enumerate(texts)
            ]
        )
        return [list(item.vector) for item in records]


def build_memory_embedding_provider() -> MemoryEmbeddingProvider:
    provider_name = settings.memory_vector_embedding_provider.strip().lower()
    model_name = settings.memory_vector_embedding_model.strip() or "memory-fake-embedding-v1"
    dimension = int(settings.memory_vector_embedding_dim)

    if provider_name == "deterministic":
        return DeterministicMemoryEmbeddingProvider(dimension=dimension, model_name=model_name)
    if provider_name == "openai_compatible":
        provider = OpenAICompatibleEmbeddingProvider(
            api_key=settings.memory_vector_embedding_api_key,
            base_url=settings.memory_vector_embedding_base_url,
            model=model_name,
            dimension=dimension,
            max_batch_size=settings.memory_vector_embedding_max_batch_size,
        )
        return RiskKnowledgeProviderAdapter(
            provider=provider,
            provider_name=provider.provider_name,
            model_name=model_name,
            dimension=dimension,
        )
    if provider_name == "dashscope":
        provider = DashScopeEmbeddingProvider(
            api_key=settings.memory_vector_embedding_api_key or settings.dashscope_api_key,
            model=model_name,
            dimension=dimension,
            output_type="dense",
            text_type="document",
            endpoint=settings.memory_vector_embedding_base_url,
        )
        return RiskKnowledgeProviderAdapter(
            provider=provider,
            provider_name=provider.provider_name,
            model_name=model_name,
            dimension=dimension,
        )
    raise ValueError(f"unsupported memory vector embedding provider: {provider_name}")
