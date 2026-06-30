"""Hybrid retrieval orchestrator for M2D-10."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.risk_knowledge.embedding.base import EmbeddingProvider
from app.risk_knowledge.embedding.factory import build_embedding_provider_from_settings
from app.risk_knowledge.retrieval.active_manifest_resolver import ActiveManifestResolver
from app.risk_knowledge.retrieval.candidate_builder import RetrievalCandidateBuilder
from app.risk_knowledge.retrieval.keyword_retriever import BM25KeywordRetriever
from app.risk_knowledge.retrieval.query_embedding import QueryEmbeddingService
from app.risk_knowledge.retrieval.query_normalizer import QueryNormalizer
from app.risk_knowledge.retrieval.rrf import RrfFusionService
from app.risk_knowledge.retrieval.schemas import HybridRetrievalResult, RetrievalQuery
from app.risk_knowledge.retrieval.vector_retriever import FaissVectorRetriever


class HybridRiskKnowledgeRetriever:
    def __init__(
        self,
        *,
        db: Session,
        provider: EmbeddingProvider | None = None,
        resolver: ActiveManifestResolver | None = None,
        vector_retriever: FaissVectorRetriever | None = None,
        keyword_retriever: BM25KeywordRetriever | None = None,
        fusion_service: RrfFusionService | None = None,
        candidate_builder: RetrievalCandidateBuilder | None = None,
    ) -> None:
        self._db = db
        self._provider = provider or build_embedding_provider_from_settings()
        self._resolver = resolver or ActiveManifestResolver(db)
        self._vector_retriever = vector_retriever or FaissVectorRetriever()
        self._keyword_retriever = keyword_retriever or BM25KeywordRetriever(db)
        self._fusion_service = fusion_service or RrfFusionService(rrf_k=settings.risk_knowledge_retrieval_rrf_k)
        self._candidate_builder = candidate_builder or RetrievalCandidateBuilder(db)
        self._normalizer = QueryNormalizer(max_query_chars=settings.risk_knowledge_retrieval_max_query_chars)

    def retrieve(self, query: RetrievalQuery) -> HybridRetrievalResult:
        normalized_query = self._normalizer.normalize(query.query)
        scope = self._resolver.resolve_scope(query)
        first_manifest = scope.manifests[0]
        query_embedding = QueryEmbeddingService(
            provider=self._provider,
            expected_dimension=first_manifest.embedding_dimension,
        ).embed_query(normalized_query)
        vector_hits = self._vector_retriever.search(query_embedding.vector, scope, top_k=query.vector_top_k)
        keyword_hits = self._keyword_retriever.search(normalized_query, scope, top_k=query.keyword_top_k)
        fused_hits = self._fusion_service.fuse(vector_hits, keyword_hits, fused_top_k=query.fused_top_k)
        candidates = self._candidate_builder.build(fused_hits, scope)
        return HybridRetrievalResult(
            query=query.query,
            normalized_query=normalized_query,
            kb_id=query.kb_id,
            scope_type=scope.scope_type,
            document_id=scope.document_id,
            version_id=scope.version_id,
            active_manifest_index_ids=list(scope.active_manifest_index_ids),
            embedding_provider=query_embedding.provider,
            embedding_model=query_embedding.model,
            embedding_dimension=query_embedding.dimension,
            candidates=candidates,
            diagnostics={
                "vector_hit_count": len(vector_hits),
                "keyword_hit_count": len(keyword_hits),
                "fused_hit_count": len(fused_hits),
            },
        )
