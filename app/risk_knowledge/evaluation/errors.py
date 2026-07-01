"""Typed errors for M2D-13 evaluation."""

from __future__ import annotations


class GoldenEvaluationError(RuntimeError):
    """Base error for M2D-13 evaluation."""


class GoldenSetLoadError(GoldenEvaluationError):
    """Raised when a golden-set file cannot be loaded."""


class GoldenSetSchemaError(GoldenEvaluationError):
    """Raised when a golden-set case fails schema validation."""


class GoldenEvaluationRuntimeError(GoldenEvaluationError):
    """Raised when runtime evaluation execution fails."""


class GoldenEvaluationReportError(GoldenEvaluationError):
    """Raised when an evaluation report cannot be built or written."""
