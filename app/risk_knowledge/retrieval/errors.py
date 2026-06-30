"""Typed errors for M2D-10 retrieval foundation."""

from __future__ import annotations


class RetrievalError(Exception):
    """Base retrieval error."""


class InvalidRetrievalQueryError(RetrievalError):
    """Raised when a retrieval query is invalid."""


class InvalidRetrievalScopeError(RetrievalError):
    """Raised when scope inputs are inconsistent."""


class RetrievalDocumentVersionMismatchError(InvalidRetrievalScopeError):
    """Raised when document/version inputs point to different assets."""


class NoActiveRetrievalScopeError(RetrievalError):
    """Raised when no active scope can be resolved."""


class NoActiveManifestError(RetrievalError):
    """Raised when a version has no active manifest."""


class InactiveManifestError(RetrievalError):
    """Raised when a manifest is not active."""


class ManifestArtifactMissingError(RetrievalError):
    """Raised when a FAISS artifact file is missing."""


class ManifestChecksumMismatchError(RetrievalError):
    """Raised when a FAISS artifact checksum mismatches."""


class VectorMappingMissingError(RetrievalError):
    """Raised when a FAISS vector mapping is missing."""


class RetrievalScopeEmbeddingMismatchError(RetrievalError):
    """Raised when a retrieval scope mixes incompatible embedding configs."""


class QueryEmbeddingDimensionMismatchError(RetrievalError):
    """Raised when a query vector does not match scope dimension."""


class QueryEmbeddingProviderError(RetrievalError):
    """Raised when the embedding provider fails during query embedding."""


class UnsupportedVectorDistanceMetricError(RetrievalError):
    """Raised when a retrieval metric is unsupported."""


class VectorSearchError(RetrievalError):
    """Raised when vector search fails."""


class KeywordSearchError(RetrievalError):
    """Raised when keyword search fails."""


class RrfFusionError(RetrievalError):
    """Raised when RRF fusion fails."""


class CandidateHydrationError(RetrievalError):
    """Raised when chunk hydration fails."""


class ChunkNotFoundForRetrievalError(CandidateHydrationError):
    """Raised when a fused hit cannot be hydrated from persisted chunks."""
