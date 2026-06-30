from __future__ import annotations

import pytest

from app.knowledge_base.config import DEFAULT_RISK_KB_ID
from app.risk_knowledge.evidence.schemas import (
    Citation,
    EvidenceGateDecision,
    EvidenceGateReason,
    EvidenceGateStatus,
    RiskEvidenceBundle,
    SelectedEvidence,
)
from app.risk_knowledge.retrieval.schemas import RetrievalScopeType


def _build_selected_evidence(*, citation_id: str = "cite_risk_1") -> SelectedEvidence:
    return SelectedEvidence(
        evidence_id="evid_risk_1",
        candidate_id="cand_risk_1",
        chunk_id="risk_chunk_001",
        document_id="risk_guide",
        version_id="risk_guide_v1",
        manifest_index_id="idx_risk_guide",
        content_hash="sha256:risk-1",
        text="多头借贷通常表示借款人在短时间内向多家机构重复申请借款。",
        section_path=["风控手册", "贷前风险"],
        page_start=1,
        page_end=1,
        retrieval_fused_score=0.9,
        retrieval_fused_rank=1,
        rerank_score=0.92,
        rerank_rank=1,
        selected_rank=1,
        matched_channels=["vector", "keyword"],
    )


def _build_bundle(*, should_answer: bool, reason: EvidenceGateReason) -> RiskEvidenceBundle:
    selected = [_build_selected_evidence()] if should_answer or reason != EvidenceGateReason.NO_CANDIDATES else []
    citations = [
        Citation(
            citation_id="cite_risk_1",
            evidence_id="evid_risk_1",
            document_id="risk_guide",
            version_id="risk_guide_v1",
            chunk_id="risk_chunk_001",
            content_hash="sha256:risk-1",
            section_path=["风控手册", "贷前风险"],
            page_start=1,
            page_end=1,
            manifest_index_id="idx_risk_guide",
            evidence_rank=1,
        )
    ] if selected else []
    return RiskEvidenceBundle(
        query="什么是多头借贷风险？",
        normalized_query="什么是多头借贷风险",
        kb_id=DEFAULT_RISK_KB_ID,
        scope_type=RetrievalScopeType.KB_ACTIVE_DOCUMENTS,
        active_manifest_index_ids=["idx_risk_guide"],
        retrieval_diagnostics={"vector_hit_count": 1},
        rerank_provider="deterministic",
        rerank_model="deterministic-rerank-v1",
        selected_evidence=selected,
        citations=citations,
        gate_decision=EvidenceGateDecision(
            should_answer=should_answer,
            status=EvidenceGateStatus.SUFFICIENT if should_answer else EvidenceGateStatus.INSUFFICIENT,
            reason=reason,
            confidence=0.9 if should_answer else 0.0,
            diagnostics={"selected_count": len(selected)},
        ),
        should_answer=should_answer,
        refusal_reason=None if should_answer else reason.value,
    )


def test_risk_knowledge_query_defaults_to_default_kb_id() -> None:
    from app.risk_knowledge.service.schemas import RiskKnowledgeQuery

    query = RiskKnowledgeQuery(
        query="什么是多头借贷风险？",
        intent="risk_knowledge_qa",
    )

    assert query.kb_id == DEFAULT_RISK_KB_ID


def test_risk_knowledge_service_returns_grounded_answer_and_rendered_citations() -> None:
    from app.risk_knowledge.service.risk_knowledge_service import RiskKnowledgeService
    from app.risk_knowledge.service.schemas import (
        EvidenceContext,
        EvidenceContextItem,
        GroundedAnswerResult,
        RenderedCitation,
        RiskKnowledgeQuery,
        RouteDecision,
    )

    class _Pipeline:
        def build_bundle(self, query):
            return _build_bundle(should_answer=True, reason=EvidenceGateReason.SUFFICIENT)

    class _RoutePolicy:
        def decide(self, query):
            return RouteDecision(should_route=True, reason="risk_concept", target_kb_id=query.kb_id)

    class _ContextBuilder:
        def build(self, bundle):
            return EvidenceContext(
                query=bundle.query,
                evidence_items=[
                    EvidenceContextItem(
                        citation_id="cite_risk_1",
                        text=bundle.selected_evidence[0].text,
                        document_title="风控手册",
                        section_path=["风控手册", "贷前风险"],
                        page_start=1,
                        page_end=1,
                        rerank_score=0.92,
                        evidence_rank=1,
                    )
                ],
                citation_map={citation.citation_id: citation for citation in bundle.citations},
                total_chars=len(bundle.selected_evidence[0].text),
            )

    class _Synthesizer:
        def synthesize(self, request):
            return GroundedAnswerResult(
                answer="多头借贷风险表示借款人短时间内向多家机构重复申请借款。[cite_risk_1]",
                used_citation_ids=["cite_risk_1"],
                provider="deterministic",
                model="deterministic-answer-v1",
            )

    class _Renderer:
        def render(self, bundle):
            return [
                RenderedCitation(
                    citation_id="cite_risk_1",
                    label="[1] 风控手册 / 贷前风险 / p.1",
                    document_id="risk_guide",
                    document_title="风控手册",
                    version_id="risk_guide_v1",
                    chunk_id="risk_chunk_001",
                    section_path="风控手册 / 贷前风险",
                    page_start=1,
                    page_end=1,
                )
            ]

    service = RiskKnowledgeService(
        pipeline=_Pipeline(),
        route_policy=_RoutePolicy(),
        context_builder=_ContextBuilder(),
        synthesizer=_Synthesizer(),
        citation_renderer=_Renderer(),
    )

    result = service.answer(
        RiskKnowledgeQuery(query="什么是多头借贷风险？", intent="risk_knowledge_qa")
    )

    assert result.answer_type == "grounded_answer"
    assert result.should_answer is True
    assert result.citations[0].citation_id == "cite_risk_1"
    assert "[cite_risk_1]" in result.answer
    assert result.used_citation_ids == ["cite_risk_1"]


def test_risk_knowledge_service_returns_refusal_without_calling_synthesizer() -> None:
    from app.risk_knowledge.service.risk_knowledge_service import RiskKnowledgeService
    from app.risk_knowledge.service.schemas import RiskKnowledgeQuery, RouteDecision

    synthesizer_called = {"value": False}

    class _Pipeline:
        def build_bundle(self, query):
            return _build_bundle(
                should_answer=False,
                reason=EvidenceGateReason.BELOW_MIN_SCORE,
            )

    class _RoutePolicy:
        def decide(self, query):
            return RouteDecision(should_route=True, reason="risk_concept", target_kb_id=query.kb_id)

    class _Synthesizer:
        def synthesize(self, request):
            synthesizer_called["value"] = True
            raise AssertionError("synthesizer must not be called for refusal path")

    service = RiskKnowledgeService(
        pipeline=_Pipeline(),
        route_policy=_RoutePolicy(),
        synthesizer=_Synthesizer(),
    )

    result = service.answer(
        RiskKnowledgeQuery(query="什么是多头借贷风险？", intent="risk_knowledge_qa")
    )

    assert result.answer_type == "refusal"
    assert result.should_answer is False
    assert result.refusal_reason == "below_min_score"
    assert synthesizer_called["value"] is False


def test_risk_knowledge_service_wraps_pipeline_failures() -> None:
    from app.risk_knowledge.service.errors import RiskEvidenceUnavailableError
    from app.risk_knowledge.service.risk_knowledge_service import RiskKnowledgeService
    from app.risk_knowledge.service.schemas import RiskKnowledgeQuery, RouteDecision

    class _BrokenPipeline:
        def build_bundle(self, query):
            raise RuntimeError("pipeline exploded")

    class _RoutePolicy:
        def decide(self, query):
            return RouteDecision(should_route=True, reason="risk_concept", target_kb_id=query.kb_id)

    service = RiskKnowledgeService(
        pipeline=_BrokenPipeline(),
        route_policy=_RoutePolicy(),
    )

    with pytest.raises(RiskEvidenceUnavailableError):
        service.answer(
            RiskKnowledgeQuery(query="什么是多头借贷风险？", intent="risk_knowledge_qa")
        )
