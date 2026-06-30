"""Real OpenAI-compatible embedding provider for M2D-8."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from importlib import import_module

from app.core.config import settings
from app.risk_knowledge.embedding.errors import (
    EmbeddingDimensionMismatchError,
    EmbeddingInputError,
    EmbeddingProviderError,
    EmbeddingProviderUnavailableError,
)
from app.risk_knowledge.embedding.schemas import EmbeddingInput, EmbeddingVectorResult


def build_vector_checksum(vector: Iterable[float]) -> str:
    payload = json.dumps([float(item) for item in vector], ensure_ascii=False, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


class OpenAICompatibleEmbeddingProvider:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        dimension: int | None = None,
        max_batch_size: int | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.risk_knowledge_embedding_api_key
        self.base_url = base_url if base_url is not None else settings.risk_knowledge_embedding_base_url
        self.model = model if model is not None else settings.risk_knowledge_embedding_model
        self.dimension = dimension if dimension is not None else settings.risk_knowledge_embedding_dimension
        self.max_batch_size = max_batch_size if max_batch_size is not None else settings.risk_knowledge_embedding_max_batch_size

    @property
    def provider_name(self) -> str:
        return "openai_compatible"

    def embed(self, inputs: list[EmbeddingInput]) -> list[EmbeddingVectorResult]:
        if not inputs:
            raise EmbeddingInputError("embedding inputs must not be empty")
        client = self._build_client()
        results: list[EmbeddingVectorResult] = []
        for start in range(0, len(inputs), self.max_batch_size):
            batch = inputs[start : start + self.max_batch_size]
            try:
                response = client.embeddings.create(
                    model=self.model,
                    input=[item.text for item in batch],
                    dimensions=self.dimension,
                    encoding_format="float",
                )
            except Exception as exc:  # pylint: disable=broad-except
                raise EmbeddingProviderError(f"embedding provider request failed: {exc}") from exc
            if len(response.data) != len(batch):
                raise EmbeddingProviderError("embedding provider returned mismatched batch size")
            for item, payload in zip(batch, response.data):
                vector = [float(value) for value in payload.embedding]
                if len(vector) != self.dimension:
                    raise EmbeddingDimensionMismatchError(
                        f"expected dimension {self.dimension}, got {len(vector)} for chunk_id={item.chunk_id}"
                    )
                results.append(
                    EmbeddingVectorResult(
                        chunk_id=item.chunk_id,
                        content_hash=item.content_hash,
                        provider=self.provider_name,
                        model=self.model,
                        dimension=self.dimension,
                        vector=vector,
                        vector_checksum=build_vector_checksum(vector),
                    )
                )
        return results

    def _build_client(self):
        if not self.api_key:
            raise EmbeddingProviderUnavailableError("RISK_KNOWLEDGE_EMBEDDING_API_KEY is missing")
        openai_client_class = _load_openai_client_class()
        kwargs = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return openai_client_class(**kwargs)


def _load_openai_client_class():
        try:
            module = import_module("openai")
        except Exception as exc:  # pylint: disable=broad-except
            raise EmbeddingProviderUnavailableError(
                "openai package is not installed; add it to requirements before using M2D-8 embedding runtime"
            ) from exc
        return module.OpenAI
