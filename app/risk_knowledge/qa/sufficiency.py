"""Evidence sufficiency checks for PR-A Risk QA."""

from __future__ import annotations

from app.core.config import settings
from app.risk_knowledge.evidence.schemas import RiskEvidenceBundle
from app.risk_knowledge.qa.schemas import EvidenceSufficiencyResult
from app.risk_knowledge.service.schemas import EvidenceTraceItem, RiskQaWarning


class EvidenceSufficiencyChecker:
    def check(
        self,
        *,
        bundle: RiskEvidenceBundle,
        evidence_trace: list[EvidenceTraceItem],
    ) -> EvidenceSufficiencyResult:
        if not bundle.should_answer:
            return EvidenceSufficiencyResult(
                status="insufficient_evidence",
                reason=bundle.refusal_reason or bundle.gate_decision.reason.value,
                warnings=[
                    RiskQaWarning(
                        code="RISK_QA_INSUFFICIENT_EVIDENCE",
                        severity="blocker",
                        message="Evidence gate refused answer generation for the current bundle.",
                        detail={"gate_reason": bundle.gate_decision.reason.value},
                    )
                ],
            )
        if not evidence_trace:
            return EvidenceSufficiencyResult(
                status="insufficient_evidence",
                reason="no_selected_evidence",
                warnings=[
                    RiskQaWarning(
                        code="RISK_QA_INSUFFICIENT_EVIDENCE",
                        severity="blocker",
                        message="No selected evidence is available for answer generation.",
                    )
                ],
            )

        top_score = evidence_trace[0].rerank_score if evidence_trace[0].rerank_score is not None else evidence_trace[0].score
        if top_score is None or top_score < settings.risk_knowledge_evidence_min_rerank_score:
            return EvidenceSufficiencyResult(
                status="insufficient_evidence",
                reason="below_min_score",
                warnings=[
                    RiskQaWarning(
                        code="RISK_QA_LOW_RETRIEVAL_CONFIDENCE",
                        severity="blocker",
                        message="Selected evidence is below the minimum confidence threshold.",
                        detail={"top_score": top_score},
                    )
                ],
            )

        if any(not item.chunk_id or not item.document_id or not item.evidence_text.strip() for item in evidence_trace):
            return EvidenceSufficiencyResult(
                status="insufficient_evidence",
                reason="missing_required_provenance",
                warnings=[
                    RiskQaWarning(
                        code="RISK_QA_INSUFFICIENT_EVIDENCE",
                        severity="blocker",
                        message="Selected evidence is missing required provenance fields.",
                    )
                ],
            )

        has_partial_gap = any(
            item.page_start is None or not item.section_path or not item.document_version
            for item in evidence_trace
        )
        if has_partial_gap or bundle.gate_decision.status.value == "ambiguous":
            return EvidenceSufficiencyResult(
                status="partial",
                reason="partial_evidence_support",
                warnings=[
                    RiskQaWarning(
                        code="RISK_QA_PARTIAL_EVIDENCE",
                        severity="warning",
                        message="Only partial evidence support is available for this answer.",
                    )
                ],
            )

        return EvidenceSufficiencyResult(
            status="grounded",
            reason="sufficient_evidence",
            warnings=[],
        )
