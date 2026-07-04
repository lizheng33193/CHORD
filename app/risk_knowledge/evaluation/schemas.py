"""Schemas for M2D-13 golden-set evaluation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


EvaluationMode = Literal["fixture", "runtime"]


class ExpectedEvidence(_StrictModel):
    document_id: str | None = None
    version_id: str | None = None
    chunk_id: str | None = None
    content_hash: str | None = None
    section_path_contains: str | None = None
    text_contains: list[str] = Field(default_factory=list)


class ExpectedCitationRef(_StrictModel):
    document_id: str | None = None
    version_id: str | None = None
    chunk_id: str | None = None
    section_path_contains: str | None = None


class GoldenEvaluationCase(_StrictModel):
    case_id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    kb_id: str = Field(..., min_length=1)
    document_id: str | None = None
    version_id: str | None = None
    intent: Literal["risk_knowledge_qa", "profile_explanation"] = "risk_knowledge_qa"
    expected_behavior: Literal["answer", "refuse", "ambiguous"]
    expected_evidence: list[ExpectedEvidence] = Field(default_factory=list)
    expected_answer_points: list[str] = Field(default_factory=list)
    expected_citation_refs: list[ExpectedCitationRef] = Field(default_factory=list)
    expected_refusal_reason: str | None = None
    expected_route: str | None = None
    expected_grounding_status: Literal["grounded", "partial", "insufficient_evidence"] | None = None
    expected_refusal: bool | None = None
    required_evidence_keywords: list[str] = Field(default_factory=list)
    forbidden_source_types: list[str] = Field(default_factory=list)
    min_citation_count: int = Field(default=0, ge=0)
    must_include_warning_codes: list[str] = Field(default_factory=list)
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    difficulty: Literal["easy", "medium", "hard"] = "medium"

    @field_validator("query", "kb_id", mode="before")
    @classmethod
    def _normalize_required_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class EvaluationConfig(_StrictModel):
    mode: EvaluationMode
    dataset_path: str = Field(..., min_length=1)
    output_dir: str | None = None
    report_only: bool = True


class RetrievalMetrics(_StrictModel):
    recall_at_5: float = 0.0
    recall_at_10: float = 0.0
    mrr: float = 0.0
    hit_at_5: bool = False
    hit_at_10: bool = False


class RerankMetrics(_StrictModel):
    rerank_hit_at_1: bool = False
    rerank_hit_at_3: bool = False
    rerank_hit_at_5: bool = False
    rerank_mrr: float = 0.0
    rerank_uplift: float | None = None


class EvidenceSelectionMetrics(_StrictModel):
    selected_expected_evidence: bool = False
    selected_count: int = 0
    evidence_precision: float = 0.0
    evidence_recall: float = 0.0


class EvidenceGateMetrics(_StrictModel):
    expected_should_answer: bool
    actual_should_answer: bool
    gate_correct: bool
    expected_refusal_reason: str | None = None
    actual_refusal_reason: str | None = None


class CitationMetrics(_StrictModel):
    citation_present: bool = False
    citation_correct: bool = False
    citation_count: int = 0
    missing_expected_citation: bool = False
    invalid_citation_count: int = 0


class AnswerMetrics(_StrictModel):
    expected_points_total: int = 0
    matched_points: int = 0
    answer_point_recall: float = 0.0
    has_unsupported_claim: bool | None = None


class GoldenCaseResult(_StrictModel):
    case_id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    expected_behavior: Literal["answer", "refuse", "ambiguous"]
    actual_should_answer: bool
    passed: bool | None = None
    retrieval_metrics: RetrievalMetrics
    rerank_metrics: RerankMetrics
    evidence_metrics: EvidenceSelectionMetrics
    gate_metrics: EvidenceGateMetrics
    citation_metrics: CitationMetrics
    answer_metrics: AnswerMetrics
    diagnostics: dict[str, object] = Field(default_factory=dict)


class GoldenEvaluationSummary(_StrictModel):
    status: Literal["completed", "skipped", "failed"] = "completed"
    total_cases: int = 0
    answer_cases: int = 0
    refusal_cases: int = 0
    ambiguous_cases: int = 0
    retrieval_recall_at_5: float = 0.0
    retrieval_recall_at_10: float = 0.0
    retrieval_mrr: float = 0.0
    rerank_hit_at_3: float = 0.0
    evidence_precision: float = 0.0
    evidence_recall: float = 0.0
    gate_accuracy: float = 0.0
    refusal_accuracy: float = 0.0
    false_answer_rate: float = 0.0
    false_refusal_rate: float = 0.0
    citation_correctness: float = 0.0
    citation_validity_rate: float = 0.0
    answer_point_recall: float = 0.0
    context_isolation_pass_rate: float = 0.0


class RegressionThresholds(_StrictModel):
    min_retrieval_recall_at_5: float = 0.7
    min_retrieval_recall_at_10: float = 0.8
    min_gate_accuracy: float = 0.8
    max_false_answer_rate: float = 0.1
    min_citation_correctness: float = 0.8


class RegressionDecision(_StrictModel):
    advisory: bool = True
    passed: bool
    failed_thresholds: list[str] = Field(default_factory=list)
    summary: str = Field(..., min_length=1)


class GoldenEvaluationReport(_StrictModel):
    run_id: str = Field(..., min_length=1)
    created_at: str = Field(..., min_length=1)
    config: EvaluationConfig
    summary: GoldenEvaluationSummary
    case_results: list[GoldenCaseResult] = Field(default_factory=list)
    failures: list[dict[str, object]] = Field(default_factory=list)
    regression_decision: RegressionDecision
