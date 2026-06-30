"""BM25 keyword retrieval for M2D-10."""

from __future__ import annotations

from app.core.config import settings
from app.risk_knowledge.persistence.repositories import SqlAlchemyKnowledgeChunkRepository
from app.risk_knowledge.retrieval.bm25 import BM25Index, BM25IndexCache, build_scope_fingerprint
from app.risk_knowledge.retrieval.errors import KeywordSearchError
from app.risk_knowledge.retrieval.schemas import ActiveRetrievalScope, KeywordRetrievalHit

_CACHE = BM25IndexCache(max_size=settings.risk_knowledge_bm25_cache_size)


class BM25KeywordRetriever:
    def __init__(self, db) -> None:
        self._chunks = SqlAlchemyKnowledgeChunkRepository(db)

    def search(self, query: str, scope: ActiveRetrievalScope, top_k: int) -> list[KeywordRetrievalHit]:
        chunk_records = self._chunks.list_by_versions([item.version_id for item in scope.manifests])
        if not chunk_records:
            return []

        manifest_by_version = {item.version_id: item for item in scope.manifests}
        fingerprint = build_scope_fingerprint(
            scope_type=scope.scope_type.value,
            kb_id=scope.kb_id,
            manifest_ids=scope.active_manifest_index_ids,
            manifest_fingerprints=[item.build_fingerprint for item in scope.manifests],
            chunks=chunk_records,
        )
        try:
            index = None
            if len(chunk_records) <= settings.risk_knowledge_bm25_max_scope_chunks:
                index = _CACHE.get(fingerprint)
            if index is None:
                index = BM25Index.build(chunk_records)
                if len(chunk_records) <= settings.risk_knowledge_bm25_max_scope_chunks:
                    _CACHE.set(fingerprint, index)
            raw_hits = index.search(query, top_k=top_k)
        except Exception as exc:  # pylint: disable=broad-except
            raise KeywordSearchError(str(exc)) from exc

        hits: list[KeywordRetrievalHit] = []
        for hit in raw_hits:
            manifest = manifest_by_version[hit.version_id]
            hits.append(
                KeywordRetrievalHit(
                    retrieval_key=f"{manifest.manifest_index_id}:{hit.chunk_id}",
                    chunk_id=hit.chunk_id,
                    document_id=hit.doc_id,
                    version_id=hit.version_id,
                    manifest_index_id=manifest.manifest_index_id,
                    score=hit.score,
                    rank=hit.rank,
                    matched_terms=hit.matched_terms,
                )
            )
        return hits
