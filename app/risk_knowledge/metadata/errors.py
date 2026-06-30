"""Errors for M2D-7 metadata and evidence builders."""

from __future__ import annotations


class MetadataBuildError(ValueError):
    """Base error for M2D-7 pure builder failures."""


class MetadataInputMismatchError(MetadataBuildError):
    """Raised when parsed/document/version/chunk identities do not align."""


class EmptyMetadataBuildInputError(MetadataBuildError):
    """Raised when builders receive empty required inputs."""
