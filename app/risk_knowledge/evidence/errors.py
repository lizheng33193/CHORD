"""Typed evidence-layer errors for M2D-11."""

from __future__ import annotations


class EvidenceError(Exception):
    """Base evidence-layer error."""


class EvidenceSelectionError(EvidenceError):
    """Raised when evidence selection cannot proceed."""


class EvidenceGateError(EvidenceError):
    """Raised when gate evaluation cannot proceed."""


class CitationBuildError(EvidenceError):
    """Raised when citation generation fails."""


class CitationMetadataMissingError(CitationBuildError):
    """Raised when selected evidence lacks required citation metadata."""


class NoSelectedEvidenceError(EvidenceError):
    """Raised when a downstream operation requires selected evidence."""
