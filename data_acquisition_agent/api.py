"""FastAPI router. Mounted into app/main.py via include_router (Step 4)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from .schemas import (GenerateRequest, GenerateResponse, ErrorType, ErrorResponse,
                      ExecuteRequest, ExecuteResponse)
from .orchestrator import DataAcquisitionOrchestrator, OrchestratorError
from .output_writer import OutputWriterError


router = APIRouter(prefix="/api/data-acquisition", tags=["data-acquisition"])

_STATUS_MAP = {
    ErrorType.BAD_REQUEST: 400, ErrorType.PROMPT_TOO_LARGE: 400,
    ErrorType.SCHEMA_VALIDATION_FAILED: 422, ErrorType.CREDENTIAL_LEAK: 422,
    ErrorType.DANGEROUS_CODE: 422, ErrorType.DDL_POLICY_VIOLATION: 422,
    ErrorType.UPSTREAM_LLM_ERROR: 502,
    # V2 新增（docs/specs/data_acquisition_agent_v2.md §5.3）
    ErrorType.DDL_NOT_SUPPORTED_IN_V2: 422,
    ErrorType.DB_UNREACHABLE: 502,
    ErrorType.QUERY_FAILED: 422,
    ErrorType.RESULT_VALIDATION_FAILED: 422,
    ErrorType.RESULT_TOO_LARGE: 413,
    ErrorType.OUTPUT_WRITE_FAILED: 500,
}

_ORCH = None


def _run_execute_pipeline(request: ExecuteRequest, *, request_id: str):
    from .executor import run_execute_pipeline

    return run_execute_pipeline(request, request_id=request_id)


def _load_execute_errors():
    from .connection import DbUnreachableError
    from .executor import ExecutorError

    return ExecutorError, DbUnreachableError


def _get_orchestrator():
    global _ORCH
    if _ORCH is None:
        _ORCH = DataAcquisitionOrchestrator()
    return _ORCH


@router.post("/generate", response_model=GenerateResponse)
def generate(request: GenerateRequest):
    try:
        return _get_orchestrator().generate(request)
    except OrchestratorError as e:
        err = ErrorResponse(error_type=e.error_type, message=e.message,
                            request_id=e.request_id)
        return JSONResponse(status_code=_STATUS_MAP[e.error_type],
                            content=err.model_dump(mode="json"))


@router.get("/manifests")
def list_manifests() -> dict:
    """Debug: list registered country manifests. Optional in V1."""
    raise HTTPException(status_code=501, detail="not implemented (Step 4)")


@router.post("/execute", response_model=ExecuteResponse)
def execute(request: ExecuteRequest):
    """V2 受控执行：守门 → 连库 → COUNT 预检 → 执行 → 切片 → 落 per-uid。"""
    import uuid
    rid = str(uuid.uuid4())
    try:
        payload = _run_execute_pipeline(request, request_id=rid)
        return ExecuteResponse(**payload)
    except Exception as exc:
        error_type = getattr(exc, "error_type", None)
        if isinstance(error_type, str):
            try:
                error_type = ErrorType(error_type)
            except ValueError:
                error_type = None
        if error_type == ErrorType.DB_UNREACHABLE or exc.__class__.__name__ == "DbUnreachableError":
            err = ErrorResponse(error_type=ErrorType.DB_UNREACHABLE,
                message="database connection failed", request_id=rid)
            return JSONResponse(status_code=502,
                content=err.model_dump(mode="json"))
        if isinstance(exc, OutputWriterError) or error_type in _STATUS_MAP:
            err = ErrorResponse(error_type=error_type, message=getattr(exc, "message", str(exc)),
                request_id=getattr(exc, "request_id", None) or rid)
            return JSONResponse(status_code=_STATUS_MAP[error_type],
                content=err.model_dump(mode="json"))
        raise


@router.get("/healthz")
def healthz() -> dict:
    """Liveness: manifest load probe + ModelClient probe. Optional in V1."""
    raise HTTPException(status_code=501, detail="not implemented (Step 4)")
