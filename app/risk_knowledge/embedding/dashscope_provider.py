"""DashScope embedding provider for M2D-9 opt-in real embedding validation."""

from __future__ import annotations

import json
from urllib import error, request

from app.core.config import settings
from app.risk_knowledge.embedding.errors import (
    EmbeddingDimensionMismatchError,
    EmbeddingInputError,
    EmbeddingProviderError,
    EmbeddingProviderUnavailableError,
)
from app.risk_knowledge.embedding.openai_compatible_provider import build_vector_checksum
from app.risk_knowledge.embedding.schemas import EmbeddingInput, EmbeddingVectorResult

_DASHSCOPE_EMBEDDING_ENDPOINT = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"


class DashScopeEmbeddingProvider:
    max_batch_size = 10

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        dimension: int | None = None,
        output_type: str | None = None,
        text_type: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.dashscope_api_key or settings.risk_knowledge_embedding_api_key
        self.model = model if model is not None else settings.risk_knowledge_embedding_model
        self.dimension = dimension if dimension is not None else settings.risk_knowledge_embedding_dimension
        self.output_type = output_type if output_type is not None else settings.risk_knowledge_embedding_output_type
        self.text_type = text_type if text_type is not None else settings.risk_knowledge_embedding_text_type
        self.endpoint = endpoint if endpoint is not None else settings.risk_knowledge_embedding_base_url or _DASHSCOPE_EMBEDDING_ENDPOINT

    @property
    def provider_name(self) -> str:
        return "dashscope"

    def embed(self, inputs: list[EmbeddingInput]) -> list[EmbeddingVectorResult]:
        if not inputs:
            raise EmbeddingInputError("embedding inputs must not be empty")
        if not self.api_key:
            raise EmbeddingProviderUnavailableError("DASHSCOPE_API_KEY is missing")
        text_type = self._resolve_text_type(inputs)
        payload = {
            "model": self.model,
            "input": {"texts": [item.text for item in inputs]},
            "parameters": {
                "dimension": self.dimension,
                "output_type": self.output_type,
                "text_type": text_type,
            },
        }
        try:
            response = self._post_embeddings_request(payload)
        except Exception as exc:  # pylint: disable=broad-except
            raise EmbeddingProviderError(
                f"dashscope embedding request failed: {self._sanitize_error_message(str(exc))}"
            ) from exc

        embeddings_payload = response.get("output", {}).get("embeddings", [])
        if len(embeddings_payload) != len(inputs):
            raise EmbeddingProviderError("dashscope embedding provider returned mismatched batch size")

        results: list[EmbeddingVectorResult] = []
        for item, payload_item in zip(inputs, embeddings_payload):
            vector = [float(value) for value in payload_item.get("embedding", [])]
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

    def _post_embeddings_request(self, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(detail) from exc

    def _sanitize_error_message(self, message: str) -> str:
        if self.api_key:
            return message.replace(self.api_key, "[redacted]")
        return message

    def _resolve_text_type(self, inputs: list[EmbeddingInput]) -> str:
        input_types = {item.input_type for item in inputs}
        if len(input_types) != 1:
            raise EmbeddingInputError("dashscope embedding batches must use a single input_type")
        input_type = input_types.pop()
        if input_type == "query":
            return "query"
        return self.text_type
