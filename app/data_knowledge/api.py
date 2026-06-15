"""FastAPI routes for data knowledge assets."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.database import get_db
from app.auth.dependencies import get_current_user_context
from app.core.user_context import UserContext
from app.data_knowledge.schemas import (
    CatalogFieldCreateRequest,
    CatalogFieldItem,
    CatalogFieldListResponse,
    CatalogFieldUpdateRequest,
    CatalogTableCreateRequest,
    CatalogTableItem,
    CatalogTableListResponse,
    CatalogTableUpdateRequest,
    GlossaryCreateRequest,
    GlossaryItem,
    GlossaryListResponse,
    GlossaryUpdateRequest,
    SeedImportRequest,
    SeedImportResponse,
    SqlErrorCaseCreateRequest,
    SqlErrorCaseItem,
    SqlErrorCaseListResponse,
    SqlErrorCaseUpdateRequest,
    SqlExampleCreateRequest,
    SqlExampleItem,
    SqlExampleListResponse,
    SqlExampleUpdateRequest,
)
from app.data_knowledge.service import DataKnowledgeService


router = APIRouter(prefix="/api/data-knowledge", tags=["data-knowledge"])


def _service(db: Session) -> DataKnowledgeService:
    return DataKnowledgeService(db)


@router.get("/catalog/tables", response_model=CatalogTableListResponse)
def list_catalog_tables(
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> CatalogTableListResponse:
    return _service(db).list_catalog_tables(ctx=ctx)


@router.post("/catalog/tables", response_model=CatalogTableItem)
def create_catalog_table(
    body: CatalogTableCreateRequest,
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> CatalogTableItem:
    return _service(db).create_catalog_table(ctx=ctx, body=body)


@router.patch("/catalog/tables/{row_id}", response_model=CatalogTableItem)
def update_catalog_table(
    row_id: int,
    body: CatalogTableUpdateRequest,
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> CatalogTableItem:
    return _service(db).update_catalog_table(ctx=ctx, row_id=row_id, body=body)


@router.get("/catalog/fields", response_model=CatalogFieldListResponse)
def list_catalog_fields(
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> CatalogFieldListResponse:
    return _service(db).list_catalog_fields(ctx=ctx)


@router.post("/catalog/fields", response_model=CatalogFieldItem)
def create_catalog_field(
    body: CatalogFieldCreateRequest,
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> CatalogFieldItem:
    return _service(db).create_catalog_field(ctx=ctx, body=body)


@router.patch("/catalog/fields/{row_id}", response_model=CatalogFieldItem)
def update_catalog_field(
    row_id: int,
    body: CatalogFieldUpdateRequest,
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> CatalogFieldItem:
    return _service(db).update_catalog_field(ctx=ctx, row_id=row_id, body=body)


@router.get("/glossary", response_model=GlossaryListResponse)
def list_glossary(
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> GlossaryListResponse:
    return _service(db).list_glossary(ctx=ctx)


@router.post("/glossary", response_model=GlossaryItem)
def create_glossary(
    body: GlossaryCreateRequest,
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> GlossaryItem:
    return _service(db).create_glossary(ctx=ctx, body=body)


@router.patch("/glossary/{row_id}", response_model=GlossaryItem)
def update_glossary(
    row_id: int,
    body: GlossaryUpdateRequest,
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> GlossaryItem:
    return _service(db).update_glossary(ctx=ctx, row_id=row_id, body=body)


@router.get("/examples", response_model=SqlExampleListResponse)
def list_examples(
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> SqlExampleListResponse:
    return _service(db).list_examples(ctx=ctx)


@router.post("/examples", response_model=SqlExampleItem)
def create_sql_example(
    body: SqlExampleCreateRequest,
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> SqlExampleItem:
    return _service(db).create_sql_example(ctx=ctx, body=body)


@router.patch("/examples/{row_id}", response_model=SqlExampleItem)
def update_sql_example(
    row_id: int,
    body: SqlExampleUpdateRequest,
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> SqlExampleItem:
    return _service(db).update_sql_example(ctx=ctx, row_id=row_id, body=body)


@router.get("/error-cases", response_model=SqlErrorCaseListResponse)
def list_error_cases(
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> SqlErrorCaseListResponse:
    return _service(db).list_error_cases(ctx=ctx)


@router.post("/error-cases", response_model=SqlErrorCaseItem)
def create_sql_error_case(
    body: SqlErrorCaseCreateRequest,
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> SqlErrorCaseItem:
    return _service(db).create_sql_error_case(ctx=ctx, body=body)


@router.patch("/error-cases/{row_id}", response_model=SqlErrorCaseItem)
def update_sql_error_case(
    row_id: int,
    body: SqlErrorCaseUpdateRequest,
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> SqlErrorCaseItem:
    return _service(db).update_sql_error_case(ctx=ctx, row_id=row_id, body=body)


@router.post("/seed/import", response_model=SeedImportResponse)
def import_seed_bundle(
    body: SeedImportRequest,
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> SeedImportResponse:
    return _service(db).import_seed_bundle_for_ctx(ctx=ctx, bundle=body.bundle)
