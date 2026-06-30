"""FAISS indexing errors for M2D-8."""

from __future__ import annotations


class FaissIndexError(Exception):
    """Base FAISS foundation error."""


class FaissUnavailableError(FaissIndexError):
    """Raised when FAISS is unavailable in the runtime environment."""


class FaissManifestMismatchError(FaissIndexError):
    """Raised when manifest metadata does not match the embeddings/artifacts."""
