from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.dependencies import require_permission
from app.core.user_context import UserContext
from app.risk_knowledge.indexing.facade import RiskKnowledgeWorkerFacade


router = APIRouter(prefix="/api/risk-knowledge/workers", tags=["risk-knowledge-workers"])


def _worker_service() -> RiskKnowledgeWorkerFacade:
    return RiskKnowledgeWorkerFacade()


@router.get("/health")
def worker_health(_ctx: UserContext = Depends(require_permission("project:manage"))):
    return _worker_service().health()

