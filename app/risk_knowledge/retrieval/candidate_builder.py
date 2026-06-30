"""Candidate hydration for M2D-10."""

from __future__ import annotations

from app.risk_knowledge.persistence.repositories import SqlAlchemyKnowledgeChunkRepository
from app.risk_knowledge.retrieval.errors import ChunkNotFoundForRetrievalError
from app.risk_knowledge.retrieval.schemas import ActiveRetrievalScope, FusedRetrievalHit, HybridRetrievalCandidate


class RetrievalCandidateBuilder:
    def __init__(self, db) -> None:
        self._chunks = SqlAlchemyKnowledgeChunkRepository(db)

    def build(self, fused_hits: list[FusedRetrievalHit], scope: ActiveRetrievalScope) -> list[HybridRetrievalCandidate]:
        chunk_records = self._chunks.list_by_versions([item.version_id for item in scope.manifests])
        chunk_map = {(item.version_id, item.chunk_id): item for item in chunk_records}
        candidates: list[HybridRetrievalCandidate] = []
        for hit in fused_hits:
            chunk = chunk_map.get((hit.version_id, hit.chunk_id))
            if chunk is None:
                raise ChunkNotFoundForRetrievalError(
                    f"persisted chunk not found for version_id={hit.version_id} chunk_id={hit.chunk_id}"
                )
            candidates.append(
                HybridRetrievalCandidate(
                    retrieval_key=hit.retrieval_key,
                    chunk_id=hit.chunk_id,
                    document_id=hit.document_id,
                    version_id=hit.version_id,
                    manifest_index_id=hit.manifest_index_id,
                    content_hash=chunk.content_hash,
                    section_path=list(chunk.section_path_json or []),
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    text=chunk.content_text,
                    vector_raw_score=hit.vector_raw_score,
                    keyword_score=hit.keyword_score,
                    vector_rank=hit.vector_rank,
                    keyword_rank=hit.keyword_rank,
                    fused_score=hit.fused_score,
                    fused_rank=hit.fused_rank,
                    matched_channels=list(hit.matched_channels),
                )
            )
        return candidates
