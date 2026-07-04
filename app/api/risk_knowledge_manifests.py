from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.database import get_db
from app.auth.dependencies import require_permission
from app.core.user_context import UserContext
from app.risk_knowledge.indexing.facade import RiskKnowledgeManifestFacade


router = APIRouter(prefix="/api/risk-knowledge/manifests", tags=["risk-knowledge-manifests"])


def _manifest_service(db: Session) -> RiskKnowledgeManifestFacade:
    return RiskKnowledgeManifestFacade(db)


@router.get("/{manifest_id}")
def get_manifest(
    manifest_id: str,
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
):
    return _manifest_service(db).get_manifest(manifest_id)


@router.post("/{manifest_id}/activate")
def activate_manifest(
    manifest_id: str,
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
):
    return _manifest_service(db).activate_manifest(manifest_id)


@router.post("/{manifest_id}/rollback")
def rollback_manifest(
    manifest_id: str,
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
):
    return _manifest_service(db).rollback_manifest(manifest_id)

