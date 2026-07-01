"""Shared read-only trace schemas for M2D-13 evaluation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.risk_knowledge.evidence.schemas import RiskEvidenceBundle
from app.risk_knowledge.retrieval.schemas import HybridRetrievalResult, RetrievalQuery
from app.risk_knowledge.reranking.schemas import RerankResult


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RiskEvidenceBuildTrace(_StrictModel):
    retrieval_query: RetrievalQuery | None = None
    retrieval_result: HybridRetrievalResult
    rerank_result: RerankResult | None = None
    bundle: RiskEvidenceBundle
