"""Evidence normalization and artifact shaping helpers for PR-A."""

from __future__ import annotations

import hashlib

from app.risk_knowledge.evidence.schemas import RiskEvidenceBundle, SelectedEvidence
from app.risk_knowledge.retrieval.schemas import HybridRetrievalResult
from app.risk_knowledge.service.schemas import EvidenceTraceItem, RenderedCitation, RiskQaWarning


class RiskQaEvidenceManager:
    def normalize_retrieval_candidates(
        self,
        retrieval_result: HybridRetrievalResult,
    ) -> list[EvidenceTraceItem]:
        items: list[EvidenceTraceItem] = []
        for candidate in retrieval_result.candidates:
            warnings: list[str] = []
            if not candidate.chunk_id:
                warnings.append("RISK_QA_CANDIDATE_MISSING_CHUNK_ID")
            items.append(
                EvidenceTraceItem(
                    evidence_id=f"ev_{candidate.chunk_id or candidate.retrieval_key}",
                    source_type="risk_domain_knowledge",
                    document_id=candidate.document_id,
                    document_name=candidate.section_path[0] if candidate.section_path else candidate.document_id,
                    document_version=candidate.version_id,
                    section_title=candidate.section_path[-1] if candidate.section_path else None,
                    section_path=list(candidate.section_path),
                    page_start=candidate.page_start,
                    page_end=candidate.page_end,
                    chunk_id=candidate.chunk_id,
                    evidence_text=candidate.text,
                    score=candidate.fused_score,
                    warnings=warnings,
                )
            )
        return items

    def build_selected_evidence_trace(
        self,
        bundle: RiskEvidenceBundle,
        citations: list[RenderedCitation],
    ) -> list[EvidenceTraceItem]:
        citation_by_evidence_id = {citation.evidence_id: citation for citation in citations if citation.evidence_id}
        return [
            self._from_selected_evidence(evidence=item, citation=citation_by_evidence_id.get(item.evidence_id))
            for item in bundle.selected_evidence
        ]

    def build_retrieval_snapshot_id(self, query: str, retrieval_result: HybridRetrievalResult) -> str:
        payload = "::".join(
            [
                query,
                ",".join(candidate.chunk_id for candidate in retrieval_result.candidates),
                ",".join(retrieval_result.active_manifest_index_ids),
            ]
        )
        return f"rqs_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"

    @staticmethod
    def build_warning(
        *,
        code: str,
        severity: str,
        message: str,
        detail: dict[str, object] | None = None,
    ) -> RiskQaWarning:
        return RiskQaWarning(
            code=code,
            severity=severity,  # type: ignore[arg-type]
            message=message,
            detail=dict(detail or {}),
        )

    @staticmethod
    def _from_selected_evidence(
        *,
        evidence: SelectedEvidence,
        citation: RenderedCitation | None,
    ) -> EvidenceTraceItem:
        return EvidenceTraceItem(
            evidence_id=evidence.evidence_id,
            source_type="risk_domain_knowledge",
            document_id=evidence.document_id,
            document_name=evidence.section_path[0] if evidence.section_path else evidence.document_id,
            document_version=evidence.version_id,
            section_title=evidence.section_path[-1] if evidence.section_path else None,
            section_path=list(evidence.section_path),
            page_start=evidence.page_start,
            page_end=evidence.page_end,
            chunk_id=evidence.chunk_id,
            evidence_text=evidence.text,
            score=evidence.retrieval_fused_score,
            rerank_score=evidence.rerank_score,
            confidence=evidence.rerank_score,
            used_in_answer=True,
            citation_label=citation.label if citation is not None else None,
            warnings=[],
        )
