from __future__ import annotations

from app.risk_knowledge.evidence.schemas import (
    EvidenceGateDecision,
    EvidenceGateReason,
    EvidenceGateStatus,
    RiskEvidenceBundle,
)
from app.risk_knowledge.retrieval.schemas import RetrievalScopeType
from app.risk_knowledge.evidence.schemas import Citation


def _empty_bundle(query_text: str) -> RiskEvidenceBundle:
    return RiskEvidenceBundle(
        query=query_text,
        normalized_query=query_text,
        kb_id="risk_domain_knowledge",
        scope_type=RetrievalScopeType.KB_ACTIVE_DOCUMENTS,
        active_manifest_index_ids=[],
        retrieval_diagnostics={},
        rerank_provider="deterministic",
        rerank_model="deterministic-rerank-v1",
        selected_evidence=[],
        citations=[],
        gate_decision=EvidenceGateDecision(
            should_answer=False,
            status=EvidenceGateStatus.INSUFFICIENT,
            reason=EvidenceGateReason.NO_CANDIDATES,
            diagnostics={},
        ),
        should_answer=False,
        refusal_reason="no_candidates",
    )


def test_deterministic_answer_synthesizer_uses_only_evidence_context() -> None:
    from app.risk_knowledge.service.answer_synthesizer import DeterministicAnswerSynthesizer
    from app.risk_knowledge.service.schemas import (
        EvidenceContext,
        EvidenceContextItem,
        GroundedAnswerRequest,
    )

    context = EvidenceContext(
        query="什么是多头借贷风险？",
        evidence_items=[
            EvidenceContextItem(
                citation_id="cite_risk_1",
                text="多头借贷通常表示借款人在短时间内向多家机构重复申请借款。",
                document_title="风控手册",
                section_path=["风控手册", "贷前风险"],
                page_start=1,
                page_end=1,
                rerank_score=0.92,
                evidence_rank=1,
            )
        ],
        citation_map={
            "cite_risk_1": Citation(
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
        },
        total_chars=32,
    )

    result = DeterministicAnswerSynthesizer().synthesize(
        GroundedAnswerRequest(
            query="什么是多头借贷风险？",
            evidence_context=context,
            answer_style="concise",
            language="zh",
        )
    )

    assert "多头借贷通常表示借款人在短时间内向多家机构重复申请借款" in result.answer
    assert "[cite_risk_1]" in result.answer
    assert result.used_citation_ids == ["cite_risk_1"]


def test_route_policy_is_conservative_for_data_like_queries() -> None:
    from app.risk_knowledge.service.route_policy import RiskKnowledgeRoutePolicy
    from app.risk_knowledge.service.schemas import RiskKnowledgeQuery

    policy = RiskKnowledgeRoutePolicy()

    routed = policy.decide(
        RiskKnowledgeQuery(query="什么是多头借贷风险？", intent="risk_knowledge_qa")
    )
    blocked = policy.decide(
        RiskKnowledgeQuery(query="统计逾期用户数量", intent="risk_knowledge_qa")
    )
    ambiguous = policy.decide(
        RiskKnowledgeQuery(query="查询用户123的风险画像", intent="risk_knowledge_qa")
    )

    assert routed.should_route is True
    assert blocked.should_route is False
    assert ambiguous.should_route is False


def test_profile_explanation_adapter_builds_profile_explanation_query() -> None:
    from app.risk_knowledge.service.profile_explanation_adapter import ProfileExplanationAdapter
    from app.risk_knowledge.service.schemas import (
        ProfileExplanationRequest,
        RiskKnowledgeAnswer,
        RiskKnowledgeQuery,
    )

    captured = {"query": None}

    class _Service:
        def answer(self, query: RiskKnowledgeQuery) -> RiskKnowledgeAnswer:
            captured["query"] = query
            return RiskKnowledgeAnswer(
                query=query.query,
                normalized_query=query.query,
                answer="已解释",
                answer_type="grounded_answer",
                should_answer=True,
                refusal_reason=None,
                evidence_bundle=_empty_bundle(query.query),
                citations=[],
                used_citation_ids=[],
                diagnostics={"source": query.source},
            )

    adapter = ProfileExplanationAdapter(service=_Service())
    result = adapter.explain(
        ProfileExplanationRequest(
            profile_facts=["短期多次申请", "高频进入借款页"],
            kb_id="risk_domain_knowledge",
            user_id="u-1",
        )
    )

    assert result.answer == "已解释"
    assert captured["query"] is not None
    assert captured["query"].intent == "profile_explanation"
    assert "短期多次申请" in captured["query"].query
    assert "高频进入借款页" in captured["query"].query
