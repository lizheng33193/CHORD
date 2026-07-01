"""Consumer-facing risk knowledge service for M2D-12."""

from __future__ import annotations

from app.risk_knowledge.evidence.schemas import RiskEvidenceBundle
from app.risk_knowledge.evidence.errors import EvidenceError
from app.risk_knowledge.retrieval.schemas import (
    HybridRetrievalCandidate,
    HybridRetrievalResult,
    RetrievalQuery,
)
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
    RiskKnowledgeAnswerTrace,
    RiskKnowledgeQuery,
)
from app.risk_knowledge.traces import RiskEvidenceBuildTrace


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
        return self.answer_with_trace(query).answer

    def answer_with_trace(self, query: RiskKnowledgeQuery) -> RiskKnowledgeAnswerTrace:
        route = self._route_policy.decide(query)
        if not route.should_route:
            raise RiskKnowledgeRoutingError(route.reason)
        try:
            if hasattr(self._pipeline, "build_trace"):
                build_trace = self._pipeline.build_trace(query)
            else:
                bundle = self._pipeline.build_bundle(query)
                build_trace = _build_fallback_trace(query, bundle)
        except (RetrievalError, RerankerError, EvidenceError, RuntimeError) as exc:
            raise RiskEvidenceUnavailableError(str(exc)) from exc
        bundle = build_trace.bundle

        citations = self._citation_renderer.render(bundle)
        diagnostics: dict[str, object] = {
            "route_reason": route.reason,
            "rerank_provider": bundle.rerank_provider,
            "rerank_model": bundle.rerank_model,
            "selected_count": len(bundle.selected_evidence),
        }
        if not bundle.should_answer:
            answer = self._refusal_builder.build(
                query=query, bundle=bundle, citations=citations, diagnostics=diagnostics
            )
            return RiskKnowledgeAnswerTrace(query=query, build_trace=build_trace, answer=answer)

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
        answer = RiskKnowledgeAnswer(
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
        return RiskKnowledgeAnswerTrace(query=query, build_trace=build_trace, answer=answer)


def build_risk_knowledge_service_from_settings() -> RiskKnowledgeService:
    return RiskKnowledgeService(
        pipeline=RiskEvidencePipeline(),
        route_policy=RiskKnowledgeRoutePolicy(),
    )


def _build_fallback_trace(query: RiskKnowledgeQuery, bundle: RiskEvidenceBundle) -> RiskEvidenceBuildTrace:
    retrieval_result = HybridRetrievalResult(
        query=bundle.query,
        normalized_query=bundle.normalized_query,
        kb_id=bundle.kb_id,
        scope_type=bundle.scope_type,
        active_manifest_index_ids=list(bundle.active_manifest_index_ids),
        embedding_provider="unknown",
        embedding_model="unknown",
        embedding_dimension=1,
        candidates=[
            HybridRetrievalCandidate(
                retrieval_key=f"{item.manifest_index_id}:{item.chunk_id}",
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                version_id=item.version_id,
                manifest_index_id=item.manifest_index_id,
                content_hash=item.content_hash,
                section_path=item.section_path,
                page_start=item.page_start,
                page_end=item.page_end,
                text=item.text,
                vector_raw_score=None,
                keyword_score=None,
                vector_rank=None,
                keyword_rank=None,
                fused_score=item.retrieval_fused_score,
                fused_rank=item.retrieval_fused_rank,
                matched_channels=item.matched_channels,
            )
            for item in bundle.selected_evidence
        ],
        diagnostics=dict(bundle.retrieval_diagnostics),
    )
    return RiskEvidenceBuildTrace(
        retrieval_query=RetrievalQuery(
            query=query.query,
            kb_id=query.kb_id,
            version_id=query.version_id,
            document_id=query.document_id,
        ),
        retrieval_result=retrieval_result,
        rerank_result=None,
        bundle=bundle,
    )
