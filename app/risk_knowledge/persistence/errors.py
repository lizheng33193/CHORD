"""Persistence-layer errors for M2D-8."""

from __future__ import annotations


class RiskKnowledgePersistenceError(Exception):
    """Base error for M2D-8 persistence failures."""


class ChunkContentConflictError(RiskKnowledgePersistenceError):
    """Raised when the same persisted chunk identity is reused with different content."""


class EmbeddingMetadataConflictError(RiskKnowledgePersistenceError):
    """Raised when persisted embedding metadata conflicts with an existing record."""
