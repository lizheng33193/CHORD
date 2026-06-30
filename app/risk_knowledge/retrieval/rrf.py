"""Rank reciprocal fusion for M2D-10."""

from __future__ import annotations

from app.risk_knowledge.retrieval.errors import RrfFusionError
from app.risk_knowledge.retrieval.schemas import FusedRetrievalHit, KeywordRetrievalHit, VectorRetrievalHit


class RrfFusionService:
    def __init__(self, *, rrf_k: int = 60) -> None:
        self._rrf_k = rrf_k

    def fuse(
        self,
        vector_hits: list[VectorRetrievalHit],
        keyword_hits: list[KeywordRetrievalHit],
        fused_top_k: int,
    ) -> list[FusedRetrievalHit]:
        try:
            fused: dict[str, FusedRetrievalHit] = {}
            for hit in vector_hits:
                fused[hit.retrieval_key] = FusedRetrievalHit(
                    retrieval_key=hit.retrieval_key,
                    chunk_id=hit.chunk_id,
                    document_id=hit.document_id,
                    version_id=hit.version_id,
                    manifest_index_id=hit.manifest_index_id,
                    vector_raw_score=hit.raw_score,
                    keyword_score=None,
                    vector_rank=hit.rank,
                    keyword_rank=None,
                    fused_score=1.0 / (self._rrf_k + hit.rank),
                    fused_rank=1,
                    matched_channels=["vector"],
                )
            for hit in keyword_hits:
                current = fused.get(hit.retrieval_key)
                score = 1.0 / (self._rrf_k + hit.rank)
                if current is None:
                    fused[hit.retrieval_key] = FusedRetrievalHit(
                        retrieval_key=hit.retrieval_key,
                        chunk_id=hit.chunk_id,
                        document_id=hit.document_id,
                        version_id=hit.version_id,
                        manifest_index_id=hit.manifest_index_id,
                        vector_raw_score=None,
                        keyword_score=hit.score,
                        vector_rank=None,
                        keyword_rank=hit.rank,
                        fused_score=score,
                        fused_rank=1,
                        matched_channels=["keyword"],
                    )
                    continue
                channels = list(current.matched_channels)
                if "keyword" not in channels:
                    channels.append("keyword")
                fused[hit.retrieval_key] = current.model_copy(
                    update={
                        "keyword_score": hit.score,
                        "keyword_rank": hit.rank,
                        "fused_score": current.fused_score + score,
                        "matched_channels": channels,
                    }
                )
            ordered = sorted(
                fused.values(),
                key=lambda item: (-item.fused_score, item.retrieval_key),
            )[:fused_top_k]
            return [
                item.model_copy(update={"fused_rank": rank})
                for rank, item in enumerate(ordered, start=1)
            ]
        except Exception as exc:  # pylint: disable=broad-except
            raise RrfFusionError(str(exc)) from exc
