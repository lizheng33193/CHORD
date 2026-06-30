"""Typed reranking errors for M2D-11."""

from __future__ import annotations


class RerankerError(Exception):
    """Base reranking error."""


class InvalidRerankRequestError(RerankerError):
    """Raised when a rerank request is invalid before provider execution."""


class RerankerProviderConfigError(RerankerError):
    """Raised when provider configuration is missing or invalid."""


class RerankerProviderError(RerankerError):
    """Raised when the underlying reranker provider call fails."""


class RerankerResultMismatchError(RerankerError):
    """Raised when provider output cannot be mapped to the request candidates."""
