"""Runtime errors for M2D-9 indexing orchestration."""

from __future__ import annotations


class IndexingRuntimeError(Exception):
    """Base error for M2D-9 indexing runtime failures."""


class IndexingLockConflictError(IndexingRuntimeError):
    """Raised when a version-level indexing lock is already held."""


class IndexingLockLostError(IndexingRuntimeError):
    """Raised when a runner loses the version-level Redis lock mid-flight."""


class IndexingRedisStateError(IndexingRuntimeError):
    """Raised when Redis runtime state cannot be read or written."""


class IndexingJobNotRetryableError(IndexingRuntimeError):
    """Raised when a failed job cannot be retried under M2D-9 rules."""


class IndexingArtifactError(IndexingRuntimeError):
    """Raised when FAISS artifacts cannot be safely persisted or validated."""
