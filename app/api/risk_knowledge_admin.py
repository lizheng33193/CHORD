"""FastAPI routes for M2D-14A knowledge base admin APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.auth.database import get_db
from app.auth.dependencies import require_permission
from app.core.user_context import UserContext
from app.risk_knowledge.admin.errors import KnowledgeBaseAdminError
from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService
from app.risk_knowledge.admin.retrieval_debug_service import RetrievalDebugService
from app.risk_knowledge.admin.schemas import (
    DebugRetrieveRequest,
    DebugRetrieveResponse,
    DocumentCreateRequest,
    DocumentListResponse,
    DocumentSummaryResponse,
    IndexingJobLaunchResponse,
    IndexingJobListResponse,
    IndexingJobSummaryResponse,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseListResponse,
    KnowledgeBaseSummaryResponse,
    UploadVersionResult,
    VersionActivateRequest,
    VersionActivateResponse,
    VersionListResponse,
    VersionSummaryResponse,
)
from app.risk_knowledge.admin.service import KnowledgeBaseAdminService
from app.risk_knowledge.admin.upload_service import KnowledgeDocumentUploadService


router = APIRouter(prefix="/api/risk-knowledge/admin", tags=["risk-knowledge-admin"])


def _service(db: Session) -> KnowledgeBaseAdminService:
    return KnowledgeBaseAdminService(db)


def _upload_service(db: Session) -> KnowledgeDocumentUploadService:
    return KnowledgeDocumentUploadService(db)


def _indexing_service(db: Session) -> IndexingAdminService:
    return IndexingAdminService(db)


def _retrieval_debug_service(db: Session) -> RetrievalDebugService:
    return RetrievalDebugService(db)


def _raise_admin_error(exc: KnowledgeBaseAdminError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


@router.post("/kbs", response_model=KnowledgeBaseSummaryResponse, status_code=status.HTTP_201_CREATED)
def create_kb(
    body: KnowledgeBaseCreateRequest,
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
) -> KnowledgeBaseSummaryResponse:
    try:
        return _service(db).create_kb(kb_id=body.kb_id, name=body.name, description=body.description)
    except KnowledgeBaseAdminError as exc:
        _raise_admin_error(exc)


@router.get("/kbs", response_model=KnowledgeBaseListResponse)
def list_kbs(
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
) -> KnowledgeBaseListResponse:
    items = _service(db).list_kbs()
    return KnowledgeBaseListResponse(items=items, total=len(items))


@router.get("/kbs/{kb_id}", response_model=KnowledgeBaseSummaryResponse)
def get_kb(
    kb_id: str,
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
) -> KnowledgeBaseSummaryResponse:
    try:
        return _service(db).get_kb(kb_id)
    except KnowledgeBaseAdminError as exc:
        _raise_admin_error(exc)


@router.post("/kbs/{kb_id}/documents", response_model=DocumentSummaryResponse, status_code=status.HTTP_201_CREATED)
def create_document(
    kb_id: str,
    body: DocumentCreateRequest,
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
) -> DocumentSummaryResponse:
    try:
        return _service(db).create_document(
            kb_id=kb_id,
            title=body.title,
            source_type=body.source_type,
            source_uri=body.source_uri,
        )
    except KnowledgeBaseAdminError as exc:
        _raise_admin_error(exc)


@router.get("/kbs/{kb_id}/documents", response_model=DocumentListResponse)
def list_documents(
    kb_id: str,
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
) -> DocumentListResponse:
    try:
        items = _service(db).list_documents(kb_id)
        return DocumentListResponse(items=items, total=len(items))
    except KnowledgeBaseAdminError as exc:
        _raise_admin_error(exc)


@router.get("/documents/{document_id}", response_model=DocumentSummaryResponse)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
) -> DocumentSummaryResponse:
    try:
        return _service(db).get_document(document_id)
    except KnowledgeBaseAdminError as exc:
        _raise_admin_error(exc)


@router.post(
    "/documents/{document_id}/versions:upload",
    response_model=UploadVersionResult,
    status_code=status.HTTP_201_CREATED,
)
def upload_document_version(
    document_id: str,
    file: UploadFile = File(...),
    version_label: str | None = Form(default=None),
    auto_index: bool = Form(default=False),
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
) -> UploadVersionResult:
    try:
        return _upload_service(db).upload_document_version(
            document_id=document_id,
            upload=file,
            version_label=version_label,
            auto_index=auto_index,
        )
    except KnowledgeBaseAdminError as exc:
        _raise_admin_error(exc)


@router.get("/documents/{document_id}/versions", response_model=VersionListResponse)
def list_versions(
    document_id: str,
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
) -> VersionListResponse:
    try:
        items = _service(db).list_versions(document_id)
        return VersionListResponse(items=items, total=len(items))
    except KnowledgeBaseAdminError as exc:
        _raise_admin_error(exc)


@router.get("/versions/{version_id}", response_model=VersionSummaryResponse)
def get_version(
    version_id: str,
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
) -> VersionSummaryResponse:
    try:
        return _service(db).get_version(version_id)
    except KnowledgeBaseAdminError as exc:
        _raise_admin_error(exc)


@router.post("/versions/{version_id}:index", response_model=IndexingJobLaunchResponse)
def index_version(
    version_id: str,
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
) -> IndexingJobLaunchResponse:
    try:
        return _indexing_service(db).start_index(version_id)
    except KnowledgeBaseAdminError as exc:
        _raise_admin_error(exc)


@router.post("/versions/{version_id}:rebuild", response_model=IndexingJobLaunchResponse)
def rebuild_version(
    version_id: str,
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
) -> IndexingJobLaunchResponse:
    try:
        return _indexing_service(db).start_rebuild(version_id)
    except KnowledgeBaseAdminError as exc:
        _raise_admin_error(exc)


@router.post("/versions/{version_id}:activate", response_model=VersionActivateResponse)
def activate_version(
    version_id: str,
    body: VersionActivateRequest,
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
) -> VersionActivateResponse:
    try:
        return _indexing_service(db).activate_version(
            version_id,
            manifest_index_id=body.manifest_index_id,
        )
    except KnowledgeBaseAdminError as exc:
        _raise_admin_error(exc)


@router.get("/indexing-jobs/{job_id}", response_model=IndexingJobSummaryResponse)
def get_indexing_job(
    job_id: str,
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
) -> IndexingJobSummaryResponse:
    try:
        return _indexing_service(db).get_job(job_id)
    except KnowledgeBaseAdminError as exc:
        _raise_admin_error(exc)


@router.get("/indexing-jobs", response_model=IndexingJobListResponse)
def list_indexing_jobs(
    kb_id: str | None = None,
    document_id: str | None = None,
    version_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
) -> IndexingJobListResponse:
    items = _indexing_service(db).list_jobs(
        kb_id=kb_id,
        document_id=document_id,
        version_id=version_id,
        status=status_filter,
    )
    return IndexingJobListResponse(items=items, total=len(items))


@router.post("/indexing-jobs/{job_id}:retry", response_model=IndexingJobLaunchResponse)
def retry_indexing_job(
    job_id: str,
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
) -> IndexingJobLaunchResponse:
    try:
        return _indexing_service(db).retry_job(job_id)
    except KnowledgeBaseAdminError as exc:
        _raise_admin_error(exc)


@router.post("/debug/retrieve", response_model=DebugRetrieveResponse)
def debug_retrieve(
    body: DebugRetrieveRequest,
    db: Session = Depends(get_db),
    _ctx: UserContext = Depends(require_permission("project:manage")),
) -> DebugRetrieveResponse:
    return _retrieval_debug_service(db).debug_retrieve(body)
