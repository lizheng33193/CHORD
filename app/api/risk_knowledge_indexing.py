from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.database import get_db
from app.auth.dependencies import require_permission
from app.core.user_context import UserContext
from app.risk_knowledge.indexing.facade import RiskKnowledgeIndexingFacade


router = APIRouter(prefix="/api/risk-knowledge/indexing", tags=["risk-knowledge-indexing"])


def _indexing_service(db: Session) -> RiskKnowledgeIndexingFacade:
    return RiskKnowledgeIndexingFacade(db)


@router.post("/jobs")
def submit_job(
    body: dict,
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
):
    return _indexing_service(db).submit_job(
        version_id=body["version_id"],
        idempotency_key=body.get("idempotency_key"),
    )


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
):
    return _indexing_service(db).get_job(job_id)


@router.post("/jobs/{job_id}/retry")
def retry_job(
    job_id: str,
    body: dict,
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
):
    return _indexing_service(db).retry_job(job_id, idempotency_key=body.get("idempotency_key"))


@router.post("/rebuild")
def rebuild(
    body: dict,
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
):
    return _indexing_service(db).rebuild(
        version_id=body["version_id"],
        idempotency_key=body.get("idempotency_key"),
    )

