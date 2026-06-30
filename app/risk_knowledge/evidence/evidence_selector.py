"""Select evidence from retrieval candidates using normalized rerank results."""

from __future__ import annotations

from app.risk_knowledge.evidence.schemas import (
    EvidenceSelectionConfig,
    EvidenceSelectionResult,
    SelectedEvidence,
)
from app.risk_knowledge.retrieval.schemas import HybridRetrievalResult
from app.risk_knowledge.reranking.rerank_service import build_candidate_id
from app.risk_knowledge.reranking.schemas import RerankResult


class EvidenceSelector:
    def select(
        self,
        *,
        retrieval_result: HybridRetrievalResult,
        rerank_result: RerankResult,
        config: EvidenceSelectionConfig,
    ) -> EvidenceSelectionResult:
        candidates_by_id = {
            build_candidate_id(
                manifest_index_id=candidate.manifest_index_id,
                document_id=candidate.document_id,
                version_id=candidate.version_id,
                chunk_id=candidate.chunk_id,
                content_hash=candidate.content_hash,
            ): candidate
            for candidate in retrieval_result.candidates
        }
        selected: list[SelectedEvidence] = []
        selected_chunk_ids: set[str] = set()
        selected_content_hashes: set[str] = set()
        skipped_by_duplicate = 0
        skipped_by_total_chars = 0
        selected_total_chars = 0

        for item in sorted(rerank_result.items, key=lambda current: current.rerank_rank):
            if item.rerank_score < config.min_rerank_score:
                continue
            candidate = candidates_by_id.get(item.candidate_id or "")
            if candidate is None:
                continue
            if candidate.chunk_id in selected_chunk_ids:
                skipped_by_duplicate += 1
                continue
            if config.dedup_by_content_hash and candidate.content_hash and candidate.content_hash in selected_content_hashes:
                skipped_by_duplicate += 1
                continue
            candidate_text_length = len(candidate.text)
            if selected_total_chars + candidate_text_length > config.max_total_chars:
                skipped_by_total_chars += 1
                continue
            selected.append(
                SelectedEvidence(
                    evidence_id=f"ev_{candidate.chunk_id}",
                    candidate_id=item.candidate_id or "",
                    chunk_id=candidate.chunk_id,
                    document_id=candidate.document_id,
                    version_id=candidate.version_id,
                    manifest_index_id=candidate.manifest_index_id,
                    content_hash=candidate.content_hash,
                    text=candidate.text,
                    section_path=list(candidate.section_path),
                    page_start=candidate.page_start,
                    page_end=candidate.page_end,
                    retrieval_fused_score=candidate.fused_score,
                    retrieval_fused_rank=candidate.fused_rank,
                    rerank_score=item.rerank_score,
                    rerank_rank=item.rerank_rank,
                    selected_rank=len(selected) + 1,
                    matched_channels=list(candidate.matched_channels),
                )
            )
            selected_total_chars += candidate_text_length
            selected_chunk_ids.add(candidate.chunk_id)
            if candidate.content_hash:
                selected_content_hashes.add(candidate.content_hash)
            if len(selected) >= config.max_evidence_count:
                break

        return EvidenceSelectionResult(
            selected_evidence=selected,
            diagnostics={
                "skipped_by_total_chars": skipped_by_total_chars,
                "skipped_by_duplicate": skipped_by_duplicate,
                "selected_total_chars": selected_total_chars,
            },
        )
