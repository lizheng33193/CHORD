from __future__ import annotations

import asyncio

import pytest

from app.risk_knowledge.evidence.schemas import (
    EvidenceGateDecision,
    EvidenceGateReason,
    EvidenceGateStatus,
    RiskEvidenceBundle,
)
from app.risk_knowledge.retrieval.schemas import RetrievalScopeType
from app.services.orchestrator_agent import agent_loop
from app.services.orchestrator_agent.flows.select_known_flow import select_known_flow
from app.services.orchestrator_agent.schemas import NormalizedRequest
from app.services.orchestrator_agent.session_store import create_session


def _bundle(query_text: str) -> RiskEvidenceBundle:
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
            should_answer=True,
            status=EvidenceGateStatus.SUFFICIENT,
            reason=EvidenceGateReason.SUFFICIENT,
            confidence=0.9,
            diagnostics={},
        ),
        should_answer=True,
        refusal_reason=None,
    )


def test_select_known_flow_returns_risk_knowledge_answer_flow() -> None:
    request = NormalizedRequest(
        intent="risk_knowledge_answer",
        country="mx",
        request_summary="回答风控知识问题",
    )

    flow = select_known_flow(request)

    assert flow is not None
    assert type(flow).__name__ == "RiskKnowledgeAnswerFlow"


@pytest.mark.timeout(3)
def test_run_agent_loop_risk_knowledge_flow_skips_legacy_and_tool_registry(monkeypatch) -> None:
    session = create_session(country="mx")
    called = {"legacy": False}

    class _FakeService:
        def answer(self, query):
            from app.risk_knowledge.service.schemas import RiskKnowledgeAnswer

            return RiskKnowledgeAnswer(
                query=query.query,
                normalized_query=query.query,
                answer="多头借贷风险表示短期内向多家机构重复申请借款。[cite_risk_1]",
                answer_type="grounded_answer",
                should_answer=True,
                refusal_reason=None,
                evidence_bundle=_bundle(query.query),
                citations=[],
                used_citation_ids=["cite_risk_1"],
                diagnostics={},
            )

    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="risk_knowledge_answer",
            country="mx",
            request_summary="回答风控知识问题",
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.flows.risk_knowledge_answer.build_risk_knowledge_service_from_settings",
        lambda: _FakeService(),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_tool_registry",
        lambda: (_ for _ in ()).throw(AssertionError("tool registry must not load for RiskKnowledgeAnswerFlow")),
    )

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "什么是多头借贷风险？", country="mx")]

    events = asyncio.run(collect())

    assert called["legacy"] is False
    assert events[-1]["type"] == "final"
    assert "多头借贷风险" in events[-1]["final_message"]
