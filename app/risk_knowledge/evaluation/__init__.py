"""M2D-13 golden-set evaluation package."""

from app.risk_knowledge.evaluation.evaluator import RiskKnowledgeGoldenEvaluator
from app.risk_knowledge.evaluation.golden_set_loader import load_golden_cases
from app.risk_knowledge.evaluation.schemas import (
    AnswerMetrics,
    CitationMetrics,
    EvaluationConfig,
    EvaluationMode,
    EvidenceGateMetrics,
    EvidenceSelectionMetrics,
    ExpectedCitationRef,
    ExpectedEvidence,
    GoldenCaseResult,
    GoldenEvaluationCase,
    GoldenEvaluationReport,
    GoldenEvaluationSummary,
    RegressionDecision,
    RegressionThresholds,
    RerankMetrics,
    RetrievalMetrics,
)

__all__ = [
    "AnswerMetrics",
    "CitationMetrics",
    "EvaluationConfig",
    "EvaluationMode",
    "EvidenceGateMetrics",
    "EvidenceSelectionMetrics",
    "ExpectedCitationRef",
    "ExpectedEvidence",
    "GoldenCaseResult",
    "GoldenEvaluationCase",
    "GoldenEvaluationReport",
    "GoldenEvaluationSummary",
    "RegressionDecision",
    "RegressionThresholds",
    "RerankMetrics",
    "RetrievalMetrics",
    "RiskKnowledgeGoldenEvaluator",
    "load_golden_cases",
]
