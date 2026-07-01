"""Build deterministic refusal answers from evidence-gate outcomes."""

from __future__ import annotations

from app.risk_knowledge.evidence.schemas import RiskEvidenceBundle
from app.risk_knowledge.service.schemas import RenderedCitation, RiskKnowledgeAnswer, RiskKnowledgeQuery


_REFUSAL_MESSAGES = {
    "no_candidates": "当前知识库中没有检索到相关候选资料，无法基于已入库证据回答这个问题。",
    "no_rerank_hits": "当前候选资料未通过重排筛选，无法基于现有证据回答这个问题。",
    "below_min_score": "当前检索到的资料相关性不足，无法基于现有证据给出可靠回答。",
    "below_min_evidence_count": "当前可用证据数量不足，无法基于现有资料给出可靠回答。",
    "empty_evidence_text": "当前证据文本不可用，无法基于现有资料回答这个问题。",
    "provider_failure": "当前证据处理失败，暂时无法基于知识库给出可靠回答。",
}


class RefusalBuilder:
    def build(
        self,
        *,
        query: RiskKnowledgeQuery,
        bundle: RiskEvidenceBundle,
        citations: list[RenderedCitation],
        diagnostics: dict[str, object],
    ) -> RiskKnowledgeAnswer:
        reason = bundle.refusal_reason or bundle.gate_decision.reason.value
        message = _REFUSAL_MESSAGES.get(
            reason,
            "当前知识库中没有足够可靠的证据来回答这个问题，因此无法给出确定结论。",
        )
        return RiskKnowledgeAnswer(
            query=query.query,
            normalized_query=bundle.normalized_query,
            answer=message,
            answer_type="refusal",
            should_answer=False,
            refusal_reason=reason,
            evidence_bundle=bundle,
            citations=citations,
            used_citation_ids=[],
            diagnostics=diagnostics,
        )
