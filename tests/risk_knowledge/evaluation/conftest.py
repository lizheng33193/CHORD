from __future__ import annotations

from pathlib import Path

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
from app.risk_knowledge.retrieval.schemas import (
    HybridRetrievalCandidate,
    HybridRetrievalResult,
    RetrievalQuery,
    RetrievalScopeType,
)
from app.risk_knowledge.reranking.schemas import RerankItem, RerankResult
from app.risk_knowledge.service.schemas import (
    RenderedCitation,
    RiskKnowledgeAnswer,
    RiskKnowledgeAnswerTrace,
    RiskKnowledgeQuery,
    RiskEvidenceBuildTrace,
)


@pytest.fixture()
def sample_golden_path() -> Path:
    return Path(__file__).resolve().parents[2] / "fixtures" / "golden" / "risk_knowledge" / "eval_set.sample.jsonl"


def build_selected_evidence(
    *,
    chunk_id: str = "risk_chunk_001",
    document_id: str = "risk_guide",
    version_id: str = "risk_guide_v1",
    content_hash: str = "sha256:risk-1",
    text: str = "多个平台重复申请借款通常意味着更高信用风险。",
    section_path: list[str] | None = None,
    rerank_score: float = 0.93,
    rerank_rank: int = 1,
    selected_rank: int = 1,
) -> SelectedEvidence:
    return SelectedEvidence(
        evidence_id=f"evid_{chunk_id}",
        candidate_id=f"cand_{chunk_id}",
        chunk_id=chunk_id,
        document_id=document_id,
        version_id=version_id,
        manifest_index_id=f"idx_{document_id}",
        content_hash=content_hash,
        text=text,
        section_path=section_path or ["风险手册", "多头借贷"],
        page_start=1,
        page_end=1,
        retrieval_fused_score=0.9,
        retrieval_fused_rank=1,
        rerank_score=rerank_score,
        rerank_rank=rerank_rank,
        selected_rank=selected_rank,
        matched_channels=["vector", "keyword"],
    )


def build_bundle(
    *,
    should_answer: bool = True,
    selected_evidence: list[SelectedEvidence] | None = None,
    refusal_reason: str | None = None,
) -> RiskEvidenceBundle:
    selected = selected_evidence or ([build_selected_evidence()] if should_answer else [])
    citations = [
        Citation(
            citation_id=f"cite_{item.chunk_id}",
            evidence_id=item.evidence_id,
            document_id=item.document_id,
            version_id=item.version_id,
            chunk_id=item.chunk_id,
            content_hash=item.content_hash,
            section_path=item.section_path,
            page_start=item.page_start,
            page_end=item.page_end,
            manifest_index_id=item.manifest_index_id,
            evidence_rank=item.selected_rank,
        )
        for item in selected
    ]
    reason = EvidenceGateReason.SUFFICIENT if should_answer else EvidenceGateReason(refusal_reason or "no_candidates")
    return RiskEvidenceBundle(
        query="什么是多头借贷风险？",
        normalized_query="什么是多头借贷风险",
        kb_id=DEFAULT_RISK_KB_ID,
        scope_type=RetrievalScopeType.KB_ACTIVE_DOCUMENTS,
        active_manifest_index_ids=["idx_risk_guide"],
        retrieval_diagnostics={"vector_hit_count": len(selected), "keyword_hit_count": len(selected)},
        rerank_provider="deterministic",
        rerank_model="deterministic-rerank-v1",
        selected_evidence=selected,
        citations=citations,
        gate_decision=EvidenceGateDecision(
            should_answer=should_answer,
            status=EvidenceGateStatus.SUFFICIENT if should_answer else EvidenceGateStatus.INSUFFICIENT,
            reason=reason,
            confidence=0.9 if should_answer else 0.1,
            diagnostics={"selected_count": len(selected)},
        ),
        should_answer=should_answer,
        refusal_reason=None if should_answer else reason.value,
    )


def build_retrieval_result(
    *,
    candidates: list[HybridRetrievalCandidate] | None = None,
) -> HybridRetrievalResult:
    actual_candidates = candidates or [
        HybridRetrievalCandidate(
            retrieval_key="idx_risk_guide:risk_chunk_001",
            chunk_id="risk_chunk_001",
            document_id="risk_guide",
            version_id="risk_guide_v1",
            manifest_index_id="idx_risk_guide",
            content_hash="sha256:risk-1",
            section_path=["风险手册", "多头借贷"],
            page_start=1,
            page_end=1,
            text="多个平台重复申请借款通常意味着更高信用风险。",
            vector_raw_score=0.1,
            keyword_score=0.9,
            vector_rank=1,
            keyword_rank=1,
            fused_score=0.95,
            fused_rank=1,
            matched_channels=["vector", "keyword"],
        )
    ]
    return HybridRetrievalResult(
        query="什么是多头借贷风险？",
        normalized_query="什么是多头借贷风险",
        kb_id=DEFAULT_RISK_KB_ID,
        scope_type=RetrievalScopeType.KB_ACTIVE_DOCUMENTS,
        active_manifest_index_ids=["idx_risk_guide"],
        embedding_provider="deterministic",
        embedding_model="deterministic-v1",
        embedding_dimension=2,
        candidates=actual_candidates,
        diagnostics={"candidate_count": len(actual_candidates)},
    )


def build_rerank_result(*, chunk_id: str = "risk_chunk_001", score: float = 0.93, rank: int = 1) -> RerankResult:
    return RerankResult(
        provider="deterministic",
        model="deterministic-rerank-v1",
        items=[
            RerankItem(
                candidate_index=0,
                candidate_id=f"cand_{chunk_id}",
                chunk_id=chunk_id,
                rerank_score=score,
                rerank_rank=rank,
            )
        ],
    )


def build_answer(
    *,
    should_answer: bool = True,
    answer: str | None = None,
    bundle: RiskEvidenceBundle | None = None,
    citations: list[RenderedCitation] | None = None,
) -> RiskKnowledgeAnswer:
    actual_bundle = bundle or build_bundle(should_answer=should_answer, refusal_reason="no_candidates" if not should_answer else None)
    rendered = citations or [
        RenderedCitation(
            citation_id="cite_risk_chunk_001",
            label="[1] 风险手册 / 多头借贷 / p.1",
            document_id="risk_guide",
            document_title="风险手册",
            version_id="risk_guide_v1",
            chunk_id="risk_chunk_001",
            section_path="风险手册 / 多头借贷",
            page_start=1,
            page_end=1,
        )
    ]
    return RiskKnowledgeAnswer(
        query=actual_bundle.query,
        normalized_query=actual_bundle.normalized_query,
        answer=answer or (
            "多个平台重复申请借款意味着更高信用风险。[cite_risk_chunk_001]"
            if should_answer
            else "当前知识库中没有足够证据支持回答该问题。"
        ),
        answer_type="grounded_answer" if should_answer else "refusal",
        should_answer=should_answer,
        refusal_reason=None if should_answer else actual_bundle.refusal_reason,
        evidence_bundle=actual_bundle,
        citations=rendered if should_answer else [],
        used_citation_ids=["cite_risk_chunk_001"] if should_answer else [],
        diagnostics={"answer_provider": "deterministic"},
    )


def build_answer_trace(
    *,
    should_answer: bool = True,
    bundle: RiskEvidenceBundle | None = None,
    retrieval_result: HybridRetrievalResult | None = None,
    rerank_result: RerankResult | None = None,
    answer: RiskKnowledgeAnswer | None = None,
) -> RiskKnowledgeAnswerTrace:
    actual_bundle = bundle or build_bundle(should_answer=should_answer, refusal_reason="no_candidates" if not should_answer else None)
    actual_retrieval = retrieval_result or build_retrieval_result()
    actual_rerank = rerank_result if rerank_result is not None else (build_rerank_result() if actual_retrieval.candidates else None)
    actual_answer = answer or build_answer(should_answer=should_answer, bundle=actual_bundle)
    return RiskKnowledgeAnswerTrace(
        query=RiskKnowledgeQuery(query=actual_bundle.query, kb_id=actual_bundle.kb_id, intent="risk_knowledge_qa"),
        build_trace=RiskEvidenceBuildTrace(
            retrieval_query=RetrievalQuery(query=actual_bundle.query, kb_id=actual_bundle.kb_id),
            retrieval_result=actual_retrieval,
            rerank_result=actual_rerank,
            bundle=actual_bundle,
        ),
        answer=actual_answer,
    )
