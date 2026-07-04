"""Consumer-facing risk knowledge service for M2D-12."""

from __future__ import annotations

from app.risk_knowledge.context import RiskQaContextBuilder
from app.risk_knowledge.evidence.schemas import RiskEvidenceBundle
from app.risk_knowledge.evidence.errors import EvidenceError
from app.risk_knowledge.evidence.manager import RiskQaEvidenceManager
from app.risk_knowledge.qa import RiskQaPipeline
from app.risk_knowledge.qa.answer_generator import RiskQaAnswerGenerator
from app.risk_knowledge.qa.citation_validation import CitationValidator
from app.risk_knowledge.qa.schemas import RiskQaRequest
from app.risk_knowledge.retrieval.schemas import (
    HybridRetrievalCandidate,
    HybridRetrievalResult,
    RetrievalQuery,
)
from app.risk_knowledge.retrieval.errors import RetrievalError
from app.risk_knowledge.reranking.errors import RerankerError
from app.risk_knowledge.service.answer_synthesizer import DeterministicAnswerSynthesizer
from app.risk_knowledge.service.citation_renderer import CitationRenderer
from app.risk_knowledge.service.evidence_context_builder import EvidenceContextBuilder
from app.risk_knowledge.service.errors import (
    RiskEvidenceUnavailableError,
    RiskKnowledgeRoutingError,
)
from app.risk_knowledge.service.pipeline import RiskEvidencePipeline
from app.risk_knowledge.service.refusal_builder import RefusalBuilder
from app.risk_knowledge.service.route_policy import RiskKnowledgeRoutePolicy
from app.risk_knowledge.service.schemas import (
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
        self._risk_qa_pipeline = RiskQaPipeline(
            evidence_pipeline=pipeline,
            context_builder=RiskQaContextBuilder(),
            evidence_manager=RiskQaEvidenceManager(),
            answer_context_builder=self._context_builder,
            answer_generator=RiskQaAnswerGenerator(synthesizer=self._synthesizer),
            citation_renderer=self._citation_renderer,
            citation_validator=CitationValidator(),
            refusal_builder=self._refusal_builder,
        )

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
            qa_result = self._risk_qa_pipeline.run(
                RiskQaRequest(
                    query=query.query,
                    kb_id=query.kb_id,
                    user_id=query.user_id,
                    session_id=query.session_id,
                    document_id=query.document_id,
                    version_id=query.version_id,
                    intent=query.intent,
                    source=query.source,
                    answer_style=query.answer_style,
                )
            )
        except (RetrievalError, RerankerError, EvidenceError, RuntimeError) as exc:
            raise RiskEvidenceUnavailableError(str(exc)) from exc
        bundle = build_trace.bundle

        diagnostics: dict[str, object] = {
            "route_reason": route.reason,
            "rerank_provider": bundle.rerank_provider,
            "rerank_model": bundle.rerank_model,
            "selected_count": len(qa_result.evidence_trace),
        }
        diagnostics.update(
            {
                "answer_provider": qa_result.diagnostics.get("answer_provider"),
                "answer_model": qa_result.diagnostics.get("answer_model"),
                "used_citation_ids": list(qa_result.used_citation_ids),
                "retrieval_snapshot_id": qa_result.retrieval_snapshot_id,
                "blocked_context_sources": list(qa_result.blocked_context_sources),
                "grounding_status": qa_result.grounding_status,
                "warning_codes": [warning.code for warning in qa_result.warnings],
            }
        )
        answer = RiskKnowledgeAnswer(
            query=query.query,
            normalized_query=bundle.normalized_query,
            answer=qa_result.answer,
            answer_type=qa_result.answer_type,
            should_answer=qa_result.should_answer,
            refusal_reason=qa_result.refusal_reason,
            evidence_bundle=qa_result.evidence_bundle,
            grounding_status=qa_result.grounding_status,
            citations=qa_result.citations,
            evidence_trace=qa_result.evidence_trace,
            retrieval_snapshot_id=qa_result.retrieval_snapshot_id,
            blocked_context_sources=qa_result.blocked_context_sources,
            context_hash=qa_result.context_hash,
            warnings=qa_result.warnings,
            used_citation_ids=list(qa_result.used_citation_ids),
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
