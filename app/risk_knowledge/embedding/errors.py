"""Embedding errors for M2D-8."""

from __future__ import annotations


class EmbeddingError(Exception):
    """Base embedding failure."""


class EmbeddingInputError(EmbeddingError):
    """Raised when embedding input is empty or malformed."""


class EmbeddingProviderUnavailableError(EmbeddingError):
    """Raised when the embedding provider cannot be used in the current environment."""


class EmbeddingProviderError(EmbeddingError):
    """Raised when provider calls fail after provider availability is confirmed."""


class EmbeddingDimensionMismatchError(EmbeddingError):
    """Raised when returned vectors do not match the configured dimension."""
