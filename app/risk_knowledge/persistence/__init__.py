"""Persistence boundaries for M2D-8 chunk, embedding, and FAISS metadata."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "RiskKnowledgePersistenceError",
    "ChunkContentConflictError",
    "EmbeddingMetadataConflictError",
    "KnowledgeChunkPersistenceService",
]


def __getattr__(name: str) -> Any:
    if name in {
        "RiskKnowledgePersistenceError",
        "ChunkContentConflictError",
        "EmbeddingMetadataConflictError",
    }:
        module = import_module("app.risk_knowledge.persistence.errors")
        return getattr(module, name)
    if name == "KnowledgeChunkPersistenceService":
        module = import_module("app.risk_knowledge.persistence.service")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
