"""Deterministic evidence sufficiency gate for M2D-11."""

from __future__ import annotations

from app.risk_knowledge.evidence.schemas import (
    EvidenceGateDecision,
    EvidenceGateReason,
    EvidenceGateStatus,
    EvidenceSelectionConfig,
    SelectedEvidence,
)
from app.risk_knowledge.retrieval.schemas import HybridRetrievalResult
from app.risk_knowledge.reranking.schemas import RerankResult


class EvidenceGate:
    def evaluate(
        self,
        *,
        retrieval_result: HybridRetrievalResult,
        rerank_result: RerankResult,
        selected_evidence: list[SelectedEvidence],
        config: EvidenceSelectionConfig,
    ) -> EvidenceGateDecision:
        top_rerank_score = selected_evidence[0].rerank_score if selected_evidence else None
        diagnostics = {
            "rerank_provider": rerank_result.provider,
            "rerank_model": rerank_result.model,
            "top_rerank_score": top_rerank_score,
            "min_rerank_score": config.min_rerank_score,
            "selected_count": len(selected_evidence),
            "threshold_source": "m2d11_contract_default",
        }
        if not retrieval_result.candidates:
            return EvidenceGateDecision(
                should_answer=False,
                status=EvidenceGateStatus.INSUFFICIENT,
                reason=EvidenceGateReason.NO_CANDIDATES,
                diagnostics=diagnostics,
            )
        if not rerank_result.items:
            return EvidenceGateDecision(
                should_answer=False,
                status=EvidenceGateStatus.INSUFFICIENT,
                reason=EvidenceGateReason.NO_RERANK_HITS,
                diagnostics=diagnostics,
            )
        if len(selected_evidence) < config.min_evidence_count:
            return EvidenceGateDecision(
                should_answer=False,
                status=EvidenceGateStatus.INSUFFICIENT,
                reason=EvidenceGateReason.BELOW_MIN_EVIDENCE_COUNT,
                diagnostics=diagnostics,
            )
        if top_rerank_score is None or top_rerank_score < config.min_rerank_score:
            return EvidenceGateDecision(
                should_answer=False,
                status=EvidenceGateStatus.INSUFFICIENT,
                reason=EvidenceGateReason.BELOW_MIN_SCORE,
                diagnostics=diagnostics,
            )
        if any(not item.text.strip() for item in selected_evidence):
            return EvidenceGateDecision(
                should_answer=False,
                status=EvidenceGateStatus.FAILED,
                reason=EvidenceGateReason.EMPTY_EVIDENCE_TEXT,
                diagnostics=diagnostics,
            )
        return EvidenceGateDecision(
            should_answer=True,
            status=EvidenceGateStatus.SUFFICIENT,
            reason=EvidenceGateReason.SUFFICIENT,
            confidence=float(top_rerank_score),
            diagnostics=diagnostics,
        )
