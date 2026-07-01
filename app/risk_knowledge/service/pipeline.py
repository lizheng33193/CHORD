"""Thin pipeline adapter from M2D-12 queries to M2D-10/M2D-11 outputs."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.auth.database import AuthSessionLocal
from app.core.config import settings
from app.risk_knowledge.evidence.evidence_bundle_builder import RiskEvidenceBundleBuilder
from app.risk_knowledge.evidence.schemas import RiskEvidenceBundle
from app.risk_knowledge.retrieval.hybrid_retriever import HybridRiskKnowledgeRetriever
from app.risk_knowledge.retrieval.schemas import RetrievalQuery
from app.risk_knowledge.service.schemas import RiskKnowledgeQuery
from app.risk_knowledge.traces import RiskEvidenceBuildTrace


class RiskEvidencePipeline:
    """Compose retrieval and evidence assembly behind one bundle method."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = AuthSessionLocal,
        retriever_factory: Callable[[Session], HybridRiskKnowledgeRetriever] | None = None,
        bundle_builder_factory: Callable[[], RiskEvidenceBundleBuilder] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._retriever_factory = retriever_factory or (lambda db: HybridRiskKnowledgeRetriever(db=db))
        self._bundle_builder_factory = bundle_builder_factory or RiskEvidenceBundleBuilder.from_settings

    def build_bundle(self, query: RiskKnowledgeQuery) -> RiskEvidenceBundle:
        return self.build_trace(query).bundle

    def build_trace(self, query: RiskKnowledgeQuery) -> RiskEvidenceBuildTrace:
        retrieval_query = RetrievalQuery(
            query=query.query,
            kb_id=query.kb_id,
            version_id=query.version_id,
            document_id=query.document_id,
            vector_top_k=settings.risk_knowledge_retrieval_vector_top_k,
            keyword_top_k=settings.risk_knowledge_retrieval_keyword_top_k,
            fused_top_k=settings.risk_knowledge_retrieval_fused_top_k,
        )
        with self._session_factory() as db:
            retriever = self._retriever_factory(db)
            bundle_builder = self._bundle_builder_factory()
            retrieval_result = retriever.retrieve(retrieval_query)
            build_trace = bundle_builder.build_with_trace(retrieval_result)
            return build_trace.model_copy(update={"retrieval_query": retrieval_query})
