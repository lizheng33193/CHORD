"""Embedding runtime boundaries for M2D-8."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "EmbeddingProvider",
    "EmbeddingBatchService",
    "OpenAICompatibleEmbeddingProvider",
    "DashScopeEmbeddingProvider",
    "build_embedding_provider_from_settings",
    "EmbeddingInputError",
    "EmbeddingProviderUnavailableError",
    "EmbeddingProviderError",
    "EmbeddingDimensionMismatchError",
]


def __getattr__(name: str) -> Any:
    if name in {
        "EmbeddingInputError",
        "EmbeddingProviderUnavailableError",
        "EmbeddingProviderError",
        "EmbeddingDimensionMismatchError",
    }:
        module = import_module("app.risk_knowledge.embedding.errors")
        return getattr(module, name)
    if name == "EmbeddingProvider":
        module = import_module("app.risk_knowledge.embedding.base")
        return getattr(module, name)
    if name == "EmbeddingBatchService":
        module = import_module("app.risk_knowledge.embedding.batch_service")
        return getattr(module, name)
    if name == "OpenAICompatibleEmbeddingProvider":
        module = import_module("app.risk_knowledge.embedding.openai_compatible_provider")
        return getattr(module, name)
    if name == "DashScopeEmbeddingProvider":
        module = import_module("app.risk_knowledge.embedding.dashscope_provider")
        return getattr(module, name)
    if name == "build_embedding_provider_from_settings":
        module = import_module("app.risk_knowledge.embedding.factory")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
