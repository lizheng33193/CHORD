"""Consumer-facing risk knowledge service for M2D-12."""

from __future__ import annotations

from app.risk_knowledge.evidence.errors import EvidenceError
from app.risk_knowledge.retrieval.errors import RetrievalError
from app.risk_knowledge.reranking.errors import RerankerError
from app.risk_knowledge.service.answer_synthesizer import (
    DeterministicAnswerSynthesizer,
)
from app.risk_knowledge.service.citation_renderer import CitationRenderer
from app.risk_knowledge.service.evidence_context_builder import EvidenceContextBuilder
from app.risk_knowledge.service.errors import (
    CitationRenderingError,
    RiskEvidenceUnavailableError,
    RiskKnowledgeRoutingError,
)
from app.risk_knowledge.service.pipeline import RiskEvidencePipeline
from app.risk_knowledge.service.refusal_builder import RefusalBuilder
from app.risk_knowledge.service.route_policy import RiskKnowledgeRoutePolicy
from app.risk_knowledge.service.schemas import (
    GroundedAnswerRequest,
    RiskKnowledgeAnswer,
    RiskKnowledgeQuery,
)


class RiskKnowledgeService:
    def __init__(
        self,
        *,
        pipeline: RiskEvidencePipeline,
        route_policy: RiskKnowledgeRoutePolicy,
        context_builder: EvidenceContextBuilder | None = None,
        synthesizer=None,
        citation_renderer: CitationRenderer | None = None,
        refusal_builder: RefusalBuilder | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._route_policy = route_policy
        self._context_builder = context_builder or EvidenceContextBuilder()
        self._synthesizer = synthesizer or DeterministicAnswerSynthesizer()
        self._citation_renderer = citation_renderer or CitationRenderer()
        self._refusal_builder = refusal_builder or RefusalBuilder()

    def answer(self, query: RiskKnowledgeQuery) -> RiskKnowledgeAnswer:
        route = self._route_policy.decide(query)
        if not route.should_route:
            raise RiskKnowledgeRoutingError(route.reason)
        try:
            bundle = self._pipeline.build_bundle(query)
        except (RetrievalError, RerankerError, EvidenceError, RuntimeError) as exc:
            raise RiskEvidenceUnavailableError(str(exc)) from exc

        citations = self._citation_renderer.render(bundle)
        diagnostics: dict[str, object] = {
            "route_reason": route.reason,
            "rerank_provider": bundle.rerank_provider,
            "rerank_model": bundle.rerank_model,
            "selected_count": len(bundle.selected_evidence),
        }
        if not bundle.should_answer:
            return self._refusal_builder.build(
                query=query,
                bundle=bundle,
                citations=citations,
                diagnostics=diagnostics,
            )

        evidence_context = self._context_builder.build(bundle)
        synthesized = self._synthesizer.synthesize(
            GroundedAnswerRequest(
                query=query.query,
                evidence_context=evidence_context,
                answer_style=query.answer_style,
                language="zh",
            )
        )
        citation_ids = {citation.citation_id for citation in citations}
        invalid_ids = [citation_id for citation_id in synthesized.used_citation_ids if citation_id not in citation_ids]
        if invalid_ids:
            raise CitationRenderingError(
                f"synthesized answer referenced unknown citations: {', '.join(invalid_ids)}"
            )
        diagnostics.update(
            {
                "answer_provider": synthesized.provider,
                "answer_model": synthesized.model,
                "used_citation_ids": list(synthesized.used_citation_ids),
            }
        )
        return RiskKnowledgeAnswer(
            query=query.query,
            normalized_query=bundle.normalized_query,
            answer=synthesized.answer,
            answer_type="grounded_answer",
            should_answer=True,
            refusal_reason=None,
            evidence_bundle=bundle,
            citations=citations,
            used_citation_ids=list(synthesized.used_citation_ids),
            diagnostics=diagnostics,
        )


def build_risk_knowledge_service_from_settings() -> RiskKnowledgeService:
    return RiskKnowledgeService(
        pipeline=RiskEvidencePipeline(),
        route_policy=RiskKnowledgeRoutePolicy(),
    )
