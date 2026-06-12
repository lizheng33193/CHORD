"""FastAPI routes for Data Agent SQL HITL."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth.database import get_db
from app.auth.dependencies import get_current_user_context
from app.core.user_context import UserContext
from app.data_agent.schemas import (
    DataAgentEditRequest,
    DataAgentReviseRequest,
    DataAgentReviewActionRequest,
    DataAgentRunCreateRequest,
    DataAgentRunDetail,
    DataAgentRunListResponse,
)
from app.data_agent.service import DataAgentService


router = APIRouter(prefix="/api/data-agent", tags=["data-agent"])


def _service(db: Session) -> DataAgentService:
    return DataAgentService(db)


@router.post("/runs", response_model=DataAgentRunDetail, status_code=status.HTTP_201_CREATED)
def create_run(
    body: DataAgentRunCreateRequest,
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> DataAgentRunDetail:
    return _service(db).create_run(ctx=ctx, body=body)


@router.get("/runs", response_model=DataAgentRunListResponse)
def list_runs(
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> DataAgentRunListResponse:
    return _service(db).list_runs(ctx=ctx)


@router.get("/runs/{run_id}", response_model=DataAgentRunDetail)
def get_run(
    run_id: str,
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> DataAgentRunDetail:
    return _service(db).get_run_detail(ctx=ctx, run_id=run_id)


@router.post("/runs/{run_id}/approve", response_model=DataAgentRunDetail)
def approve_run(
    run_id: str,
    body: DataAgentReviewActionRequest,
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> DataAgentRunDetail:
    return _service(db).approve_run(ctx=ctx, run_id=run_id, comment=body.comment)


@router.post("/runs/{run_id}/edit", response_model=DataAgentRunDetail)
def edit_run(
    run_id: str,
    body: DataAgentEditRequest,
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> DataAgentRunDetail:
    return _service(db).edit_run(ctx=ctx, run_id=run_id, body=body)


@router.post("/runs/{run_id}/revise", response_model=DataAgentRunDetail)
def revise_run(
    run_id: str,
    body: DataAgentReviseRequest,
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> DataAgentRunDetail:
    return _service(db).revise_run(ctx=ctx, run_id=run_id, body=body)


@router.post("/runs/{run_id}/reject", response_model=DataAgentRunDetail)
def reject_run(
    run_id: str,
    body: DataAgentReviewActionRequest,
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> DataAgentRunDetail:
    return _service(db).reject_run(ctx=ctx, run_id=run_id, comment=body.comment)


@router.post("/runs/{run_id}/execute", response_model=DataAgentRunDetail)
def execute_run(
    run_id: str,
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(get_current_user_context),
) -> DataAgentRunDetail:
    return _service(db).execute_run(ctx=ctx, run_id=run_id)

