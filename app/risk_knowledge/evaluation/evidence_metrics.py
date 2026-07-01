"""Evidence and gate metrics for M2D-13."""

from __future__ import annotations

from app.risk_knowledge.evaluation.matchers import expected_evidence_matches_candidate
from app.risk_knowledge.evaluation.schemas import (
    EvidenceGateMetrics,
    EvidenceSelectionMetrics,
    GoldenEvaluationCase,
)
from app.risk_knowledge.evidence.schemas import RiskEvidenceBundle
from app.risk_knowledge.service.schemas import RiskKnowledgeAnswer


def calculate_evidence_selection_metrics(
    case: GoldenEvaluationCase,
    bundle: RiskEvidenceBundle,
) -> EvidenceSelectionMetrics:
    selected = bundle.selected_evidence
    expected = case.expected_evidence
    if not selected and not expected:
        return EvidenceSelectionMetrics(selected_count=0, evidence_precision=1.0, evidence_recall=1.0)

    matched_selected = sum(
        1 for item in selected if any(expected_evidence_matches_candidate(match, item) for match in expected)
    )
    matched_expected = sum(
        1 for match in expected if any(expected_evidence_matches_candidate(match, item) for item in selected)
    )
    precision = 1.0 if not selected else matched_selected / len(selected)
    recall = 1.0 if not expected else matched_expected / len(expected)
    return EvidenceSelectionMetrics(
        selected_expected_evidence=matched_selected > 0,
        selected_count=len(selected),
        evidence_precision=precision,
        evidence_recall=recall,
    )


def calculate_evidence_gate_metrics(
    case: GoldenEvaluationCase,
    answer: RiskKnowledgeAnswer,
) -> EvidenceGateMetrics:
    expected_should_answer = case.expected_behavior == "answer"
    if case.expected_behavior == "ambiguous":
        expected_should_answer = answer.should_answer
    expected_reason = case.expected_refusal_reason if case.expected_behavior == "refuse" else None
    actual_reason = answer.refusal_reason
    reason_ok = expected_reason is None or expected_reason == actual_reason
    gate_correct = answer.should_answer == expected_should_answer and reason_ok
    return EvidenceGateMetrics(
        expected_should_answer=expected_should_answer,
        actual_should_answer=answer.should_answer,
        gate_correct=gate_correct,
        expected_refusal_reason=expected_reason,
        actual_refusal_reason=actual_reason,
    )
