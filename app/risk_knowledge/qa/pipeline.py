"""Internal PR-A Risk QA pipeline implementation."""

from __future__ import annotations

from app.risk_knowledge.evidence.schemas import RiskEvidenceBundle
from app.risk_knowledge.context import ContextBuildRequest, RiskQaContextBuilder
from app.risk_knowledge.evidence.manager import RiskQaEvidenceManager
from app.risk_knowledge.qa.answer_generator import RiskQaAnswerGenerator
from app.risk_knowledge.qa.citation_validation import CitationValidator
from app.risk_knowledge.qa.schemas import RiskQaPipelineResult, RiskQaRequest
from app.risk_knowledge.qa.sufficiency import EvidenceSufficiencyChecker
from app.risk_knowledge.retrieval.schemas import HybridRetrievalCandidate, HybridRetrievalResult, RetrievalQuery
from app.risk_knowledge.service.citation_renderer import CitationRenderer
from app.risk_knowledge.service.evidence_context_builder import EvidenceContextBuilder
from app.risk_knowledge.service.pipeline import RiskEvidencePipeline
from app.risk_knowledge.service.refusal_builder import RefusalBuilder
from app.risk_knowledge.service.schemas import RiskKnowledgeQuery
from app.risk_knowledge.traces import RiskEvidenceBuildTrace


class RiskQaPipeline:
    def __init__(
        self,
        *,
        evidence_pipeline: RiskEvidencePipeline,
        context_builder: RiskQaContextBuilder | None = None,
        evidence_manager: RiskQaEvidenceManager | None = None,
        answer_context_builder: EvidenceContextBuilder | None = None,
        answer_generator: RiskQaAnswerGenerator | None = None,
        citation_renderer: CitationRenderer | None = None,
        citation_validator: CitationValidator | None = None,
        refusal_builder: RefusalBuilder | None = None,
    ) -> None:
        self._evidence_pipeline = evidence_pipeline
        self._context_builder = context_builder or RiskQaContextBuilder()
        self._evidence_manager = evidence_manager or RiskQaEvidenceManager()
        self._answer_context_builder = answer_context_builder or EvidenceContextBuilder()
        self._answer_generator = answer_generator or RiskQaAnswerGenerator()
        self._citation_renderer = citation_renderer or CitationRenderer()
        self._citation_validator = citation_validator or CitationValidator()
        self._refusal_builder = refusal_builder or RefusalBuilder()
        self._sufficiency_checker = EvidenceSufficiencyChecker()

    def run(self, request: RiskQaRequest) -> RiskQaPipelineResult:
        service_query = RiskKnowledgeQuery(
            query=request.query,
            kb_id=request.kb_id,
            user_id=request.user_id,
            session_id=request.session_id,
            document_id=request.document_id,
            version_id=request.version_id,
            intent=request.intent,  # type: ignore[arg-type]
            source=request.source,
            answer_style=request.answer_style,
        )
        if hasattr(self._evidence_pipeline, "build_trace"):
            build_trace = self._evidence_pipeline.build_trace(service_query)
        else:
            bundle = self._evidence_pipeline.build_bundle(service_query)
            build_trace = _build_fallback_trace(service_query, bundle)
        bundle = build_trace.bundle
        rendered_citations = self._citation_renderer.render(bundle)
        selected_evidence_trace = self._evidence_manager.build_selected_evidence_trace(bundle, rendered_citations)
        retrieval_snapshot_id = self._evidence_manager.build_retrieval_snapshot_id(
            request.query,
            build_trace.retrieval_result,
        )
        context_result = self._context_builder.build(
            ContextBuildRequest(
                task_type="risk_knowledge_answer",
                query=request.query,
                selected_evidence_ids=[item.evidence_id for item in selected_evidence_trace],
            )
        )
        sufficiency = self._sufficiency_checker.check(
            bundle=bundle,
            evidence_trace=selected_evidence_trace,
        )
        warnings = [*context_result.isolation_warnings, *sufficiency.warnings]
        diagnostics: dict[str, object] = {
            "retrieval_snapshot_id": retrieval_snapshot_id,
            "selected_count": len(selected_evidence_trace),
        }

        if sufficiency.status == "insufficient_evidence":
            refusal = self._refusal_builder.build(
                query=RiskKnowledgeQuery(
                    query=service_query.query,
                    kb_id=service_query.kb_id,
                    user_id=service_query.user_id,
                    session_id=service_query.session_id,
                    document_id=service_query.document_id,
                    version_id=service_query.version_id,
                    intent=service_query.intent,
                    source=service_query.source,
                    answer_style=service_query.answer_style,
                ),
                bundle=bundle,
                citations=rendered_citations,
                diagnostics=diagnostics,
            )
            return RiskQaPipelineResult(
                answer=refusal.answer,
                answer_type="refusal",
                should_answer=False,
                refusal_reason=refusal.refusal_reason,
                grounding_status="insufficient_evidence",
                citations=rendered_citations,
                evidence_trace=selected_evidence_trace,
                retrieval_snapshot_id=retrieval_snapshot_id,
                blocked_context_sources=context_result.blocked_context_sources,
                context_hash=context_result.context_hash,
                warnings=warnings,
                evidence_bundle=bundle,
                diagnostics=diagnostics,
            )

        answer_context = self._answer_context_builder.build(bundle)
        generated = self._answer_generator.generate(
            query=request.query,
            evidence_context=answer_context,
            answer_style=request.answer_style,
            grounding_status=sufficiency.status,
        )
        citation_result = self._citation_validator.validate(
            citations=rendered_citations,
            evidence_trace=selected_evidence_trace,
            used_citation_ids=generated.used_citation_ids,
        )
        warnings.extend(citation_result.warnings)
        if not citation_result.passed:
            warnings.extend(citation_result.blockers)
            downgrade_status = "partial" if selected_evidence_trace else "insufficient_evidence"
            answer_type = "grounded_answer" if downgrade_status == "partial" else "refusal"
            safe_answer = (
                f"当前知识库只支持部分解释，以下内容仅基于已校验的证据：{generated.answer}"
                if downgrade_status == "partial"
                else "当前知识库证据不足，无法基于已收录的风控文档给出可靠结论。"
            )
            return RiskQaPipelineResult(
                answer=safe_answer,
                answer_type=answer_type,  # type: ignore[arg-type]
                should_answer=downgrade_status != "insufficient_evidence",
                refusal_reason="citation_validation_failed" if downgrade_status == "insufficient_evidence" else None,
                grounding_status=downgrade_status,  # type: ignore[arg-type]
                citations=rendered_citations,
                evidence_trace=selected_evidence_trace,
                retrieval_snapshot_id=retrieval_snapshot_id,
                blocked_context_sources=context_result.blocked_context_sources,
                context_hash=context_result.context_hash,
                warnings=warnings,
                used_citation_ids=citation_result.used_citation_ids,
                evidence_bundle=bundle,
                diagnostics=diagnostics,
            )

        return RiskQaPipelineResult(
            answer=generated.answer,
            answer_type="grounded_answer",
            should_answer=True,
            refusal_reason=None,
            grounding_status=sufficiency.status,
            citations=rendered_citations,
            evidence_trace=selected_evidence_trace,
            retrieval_snapshot_id=retrieval_snapshot_id,
            blocked_context_sources=context_result.blocked_context_sources,
            context_hash=context_result.context_hash,
            warnings=warnings,
            used_citation_ids=generated.used_citation_ids,
            evidence_bundle=bundle,
            diagnostics={
                **diagnostics,
                "answer_provider": generated.provider,
                "answer_model": generated.model,
            },
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
