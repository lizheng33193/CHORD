"""Build LLM-safe answer context from selected evidence only."""

from __future__ import annotations

from app.core.config import settings
from app.risk_knowledge.evidence.errors import NoSelectedEvidenceError
from app.risk_knowledge.evidence.schemas import RiskEvidenceBundle
from app.risk_knowledge.service.schemas import EvidenceContext, EvidenceContextItem


class EvidenceContextBuilder:
    def __init__(self, *, max_context_chars: int | None = None) -> None:
        self._max_context_chars = max_context_chars or settings.risk_knowledge_answer_max_context_chars

    def build(self, bundle: RiskEvidenceBundle) -> EvidenceContext:
        if not bundle.selected_evidence:
            raise NoSelectedEvidenceError("selected evidence is required to build answer context")

        citation_by_evidence_id = {citation.evidence_id: citation for citation in bundle.citations}
        selected_total = 0
        items: list[EvidenceContextItem] = []
        citation_map = {}
        for evidence in sorted(bundle.selected_evidence, key=lambda item: item.selected_rank):
            citation = citation_by_evidence_id.get(evidence.evidence_id)
            if citation is None:
                continue
            next_total = selected_total + len(evidence.text)
            if items and next_total > self._max_context_chars:
                continue
            selected_total = next_total
            citation_map[citation.citation_id] = citation
            items.append(
                EvidenceContextItem(
                    citation_id=citation.citation_id,
                    text=evidence.text,
                    document_title=evidence.section_path[0] if evidence.section_path else evidence.document_id,
                    section_path=list(evidence.section_path),
                    page_start=evidence.page_start,
                    page_end=evidence.page_end,
                    rerank_score=evidence.rerank_score,
                    evidence_rank=evidence.selected_rank,
                )
            )
        if not items:
            raise NoSelectedEvidenceError("no evidence items fit into answer context")
        return EvidenceContext(
            query=bundle.query,
            evidence_items=items,
            citation_map=citation_map,
            total_chars=selected_total,
        )
