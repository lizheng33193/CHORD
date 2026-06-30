"""Typed errors for M2D-12 risk knowledge service."""

from __future__ import annotations


class RiskKnowledgeServiceError(Exception):
    """Base risk knowledge service error."""


class InvalidRiskKnowledgeQueryError(RiskKnowledgeServiceError):
    """Raised when a service query is invalid."""


class RiskKnowledgeRoutingError(RiskKnowledgeServiceError):
    """Raised when a query should not route to risk knowledge answering."""


class RiskEvidenceUnavailableError(RiskKnowledgeServiceError):
    """Raised when retrieval or evidence pipeline execution fails."""


class GroundedAnswerSynthesisError(RiskKnowledgeServiceError):
    """Raised when grounded answer generation fails."""


class CitationRenderingError(RiskKnowledgeServiceError):
    """Raised when answer citations cannot be rendered or validated."""


class ProfileExplanationAdapterError(RiskKnowledgeServiceError):
    """Raised when the profile explanation adapter cannot build a query."""
