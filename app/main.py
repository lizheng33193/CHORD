"""FastAPI application entrypoint for the user profiling multi-agent system."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.analyze import router as analyze_router
from app.api.analyze_module import router as analyze_module_router
from app.api.analyze_stream import router as analyze_stream_router
from app.auth.errors import AuthenticationError, AuthorizationError
from app.auth.router import router as auth_router
from app.api.trace import router as trace_router
from app.core.config import settings
from app.core.data_acquisition_capability import get_data_acquisition_capability
from app.ui.build_frontend import BUILT_FRONTEND_HTML, build_frontend_html

STATIC_DIR = Path(__file__).resolve().parent / "static"
LOGGER = logging.getLogger(__name__)


# Create the FastAPI application with basic project metadata.
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Minimal backend skeleton for a multi-agent user profiling system.",
)


@app.on_event("startup")
async def _validate_llm_routes_on_startup() -> None:
    """Plan #02 Task 1.2 — validate llm.routes + warn on placeholder endpoints."""
    from app.core.config import validate_llm_routes
    validate_llm_routes()
    if settings.auth_enabled:
        from app.auth.database import create_auth_schema
        from app.auth.database import AuthSessionLocal
        from app.auth.seed import seed_auth_data

        create_auth_schema()
        if settings.auth_seed_on_startup:
            with AuthSessionLocal() as db:
                seed_auth_data(db)


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(_, exc: RequestValidationError) -> JSONResponse:
    """Normalize request validation failures into 400-level business errors."""
    first_error = exc.errors()[0] if exc.errors() else {}
    message = str(first_error.get("msg") or "Invalid request payload.")
    return JSONResponse(status_code=400, content={"detail": message})


@app.exception_handler(AuthorizationError)
async def authorization_exception_handler(_, exc: AuthorizationError) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(AuthenticationError)
async def authentication_exception_handler(_, exc: AuthenticationError) -> JSONResponse:
    return JSONResponse(status_code=401, content={"detail": str(exc)})


@app.get("/", response_class=HTMLResponse, summary="Homepage")
def homepage():
    """Serve the frontend. Rebuilds from JSX sources on every request so that
    edits are visible immediately during ``uvicorn --reload`` development."""
    return HTMLResponse(build_frontend_html())


@app.get("/health", summary="Health check")
def health_check() -> dict[str, str]:
    """Return a simple status payload so the service can be monitored easily."""
    return {"status": "ok"}


@app.get(
    "/.well-known/appspecific/com.chrome.devtools.json",
    response_class=JSONResponse,
    include_in_schema=False,
)
def chrome_devtools_probe() -> dict[str, str]:
    """Silence Chrome DevTools probe requests to avoid noisy 404 logs."""
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# Register business APIs under the /api prefix.
app.include_router(analyze_router, prefix="/api", tags=["analyze"])
app.include_router(analyze_module_router, prefix="/api", tags=["analyze"])
app.include_router(analyze_stream_router, prefix="/api", tags=["analyze"])
app.include_router(auth_router)
app.include_router(trace_router)

# Orchestrator Agent SSE chat (Plan #03)
from app.api.orchestrator_routes import router as orchestrator_router

app.include_router(orchestrator_router)


def _maybe_include_data_acquisition_router() -> None:
    capability = get_data_acquisition_capability()
    if not capability.enabled:
        if capability.reason != "disabled_by_config":
            LOGGER.warning(
                "Skipping /api/data-acquisition router because capability is unavailable: %s",
                capability.reason,
            )
        return
    data_api_mod = __import__("data_acquisition_agent.api", fromlist=["router"])
    app.include_router(data_api_mod.router)


_maybe_include_data_acquisition_router()
