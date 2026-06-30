"""Embedding provider protocol for M2D-8."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.risk_knowledge.embedding.schemas import EmbeddingInput, EmbeddingVectorResult


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    def embed(self, inputs: list[EmbeddingInput]) -> list[EmbeddingVectorResult]: ...
