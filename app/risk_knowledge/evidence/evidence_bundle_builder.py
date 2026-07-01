"""Build `RiskEvidenceBundle` from retrieval and rerank outputs."""

from __future__ import annotations

from app.core.config import settings
from app.risk_knowledge.evidence.citation_builder import CitationBuilder
from app.risk_knowledge.evidence.evidence_gate import EvidenceGate
from app.risk_knowledge.evidence.evidence_selector import EvidenceSelector
from app.risk_knowledge.evidence.schemas import (
    EvidenceGateDecision,
    EvidenceGateReason,
    EvidenceGateStatus,
    EvidenceSelectionConfig,
    RiskEvidenceBundle,
)
from app.risk_knowledge.retrieval.schemas import HybridRetrievalResult
from app.risk_knowledge.reranking.factory import build_reranker_provider_from_settings
from app.risk_knowledge.reranking.provider import RerankerProvider
from app.risk_knowledge.reranking.rerank_service import RerankService
from app.risk_knowledge.reranking.schemas import RerankResult
from app.risk_knowledge.traces import RiskEvidenceBuildTrace


class RiskEvidenceBundleBuilder:
    def __init__(
        self,
        *,
        rerank_service: RerankService,
        selection_config: EvidenceSelectionConfig,
        selector: EvidenceSelector | None = None,
        gate: EvidenceGate | None = None,
        citation_builder: CitationBuilder | None = None,
    ) -> None:
        self._rerank_service = rerank_service
        self._selection_config = selection_config
        self._selector = selector or EvidenceSelector()
        self._gate = gate or EvidenceGate()
        self._citation_builder = citation_builder or CitationBuilder()

    @classmethod
    def from_provider(
        cls,
        *,
        provider: RerankerProvider,
        rerank_model: str,
        top_n: int = 10,
        max_evidence_count: int = 6,
        min_evidence_count: int = 1,
        min_rerank_score: float = 0.2,
        max_total_chars: int = 6000,
        dedup_by_content_hash: bool = True,
    ) -> "RiskEvidenceBundleBuilder":
        return cls(
            rerank_service=RerankService(provider=provider, model=rerank_model, top_n=top_n),
            selection_config=EvidenceSelectionConfig(
                max_evidence_count=max_evidence_count,
                min_evidence_count=min_evidence_count,
                min_rerank_score=min_rerank_score,
                max_total_chars=max_total_chars,
                dedup_by_content_hash=dedup_by_content_hash,
            ),
        )

    @classmethod
    def from_settings(cls) -> "RiskEvidenceBundleBuilder":
        return cls.from_provider(
            provider=build_reranker_provider_from_settings(),
            rerank_model=settings.risk_knowledge_reranker_model,
            top_n=settings.risk_knowledge_reranker_top_n,
            max_evidence_count=settings.risk_knowledge_evidence_max_count,
            min_evidence_count=settings.risk_knowledge_evidence_min_count,
            min_rerank_score=settings.risk_knowledge_evidence_min_rerank_score,
            max_total_chars=settings.risk_knowledge_evidence_max_total_chars,
            dedup_by_content_hash=settings.risk_knowledge_evidence_dedup_by_content_hash,
        )

    def build(self, retrieval_result: HybridRetrievalResult) -> RiskEvidenceBundle:
        return self.build_with_trace(retrieval_result).bundle

    def build_with_trace(self, retrieval_result: HybridRetrievalResult) -> RiskEvidenceBuildTrace:
        if not retrieval_result.candidates:
            gate_decision = EvidenceGateDecision(
                should_answer=False,
                status=EvidenceGateStatus.INSUFFICIENT,
                reason=EvidenceGateReason.NO_CANDIDATES,
                diagnostics={
                    "rerank_provider": self._rerank_service._provider.provider_name,  # pylint: disable=protected-access
                    "rerank_model": self._rerank_service._model,  # pylint: disable=protected-access
                    "top_rerank_score": None,
                    "min_rerank_score": self._selection_config.min_rerank_score,
                    "selected_count": 0,
                    "threshold_source": "m2d11_contract_default",
                },
            )
            bundle = RiskEvidenceBundle(
                query=retrieval_result.query,
                normalized_query=retrieval_result.normalized_query,
                kb_id=retrieval_result.kb_id,
                scope_type=retrieval_result.scope_type,
                active_manifest_index_ids=list(retrieval_result.active_manifest_index_ids),
                retrieval_diagnostics=dict(retrieval_result.diagnostics),
                rerank_provider=self._rerank_service._provider.provider_name,  # pylint: disable=protected-access
                rerank_model=self._rerank_service._model,  # pylint: disable=protected-access
                selected_evidence=[],
                citations=[],
                gate_decision=gate_decision,
                should_answer=False,
                refusal_reason=gate_decision.reason.value,
            )
            return RiskEvidenceBuildTrace(
                retrieval_query=None,  # type: ignore[arg-type]
                retrieval_result=retrieval_result,
                rerank_result=None,
                bundle=bundle,
            )

        rerank_result = self._rerank_service.rerank_retrieval_result(retrieval_result)
        bundle = self._build_from_rerank_result(retrieval_result=retrieval_result, rerank_result=rerank_result)
        return RiskEvidenceBuildTrace(
            retrieval_query=None,  # type: ignore[arg-type]
            retrieval_result=retrieval_result,
            rerank_result=rerank_result,
            bundle=bundle,
        )

    def _build_from_rerank_result(
        self,
        *,
        retrieval_result: HybridRetrievalResult,
        rerank_result: RerankResult,
    ) -> RiskEvidenceBundle:
        selection_result = self._selector.select(
            retrieval_result=retrieval_result,
            rerank_result=rerank_result,
            config=self._selection_config,
        )
        citations = self._citation_builder.build(selection_result.selected_evidence)
        gate_decision = self._gate.evaluate(
            retrieval_result=retrieval_result,
            rerank_result=rerank_result,
            selected_evidence=selection_result.selected_evidence,
            config=self._selection_config,
        )
        return RiskEvidenceBundle(
            query=retrieval_result.query,
            normalized_query=retrieval_result.normalized_query,
            kb_id=retrieval_result.kb_id,
            scope_type=retrieval_result.scope_type,
            active_manifest_index_ids=list(retrieval_result.active_manifest_index_ids),
            retrieval_diagnostics={
                **dict(retrieval_result.diagnostics),
                **selection_result.diagnostics,
            },
            rerank_provider=rerank_result.provider,
            rerank_model=rerank_result.model,
            selected_evidence=selection_result.selected_evidence,
            citations=citations,
            gate_decision=gate_decision,
            should_answer=gate_decision.should_answer,
            refusal_reason=None if gate_decision.should_answer else gate_decision.reason.value,
        )
