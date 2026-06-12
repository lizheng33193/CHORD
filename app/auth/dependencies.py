"""FastAPI auth dependencies."""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.database import get_db
from app.auth.errors import AuthenticationError, AuthorizationError
from app.auth.jwt import JWTError, decode_access_token
from app.auth.permissions import require_permission as require_permission_check
from app.auth.service import AuthService
from app.core.config import settings
from app.core.request_context import RequestContext
from app.core.user_context import ProjectAccessScope, UserContext


_BEARER = HTTPBearer(auto_error=False)


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)


def build_demo_user_context(request: Request | None = None) -> UserContext:
    user_id = request.headers.get("X-User-ID") if request is not None else None
    project_id = request.headers.get("X-Project-ID") if request is not None else None
    country = request.headers.get("X-Country") if request is not None else None
    effective_user_id = str(user_id or settings.auth_demo_user_id)
    effective_project_id = str(project_id or settings.auth_demo_project_id)
    effective_country = (country or settings.auth_demo_country).lower()
    permissions = (
        "profile:run",
        "profile:view",
        "trace:run",
        "trace:view",
        "data:query:generate",
        "data:query:review",
        "data:query:execute",
        "data:query:view_sql",
        "data:bucket:writeback",
        "memory:read",
        "memory:write",
        "memory:manage",
        "audit:view",
        "user:manage",
        "project:manage",
    )
    return UserContext(
        user_id=effective_user_id,
        username=request.headers.get("X-Username") if request is not None else settings.auth_demo_username,
        email=None,
        display_name=settings.auth_demo_display_name,
        roles=("admin",),
        permissions=permissions,
        project_id=effective_project_id,
        project_code=settings.auth_demo_project_code,
        country=effective_country,
        project_scopes=(
            ProjectAccessScope(
                project_id=effective_project_id,
                project_code=settings.auth_demo_project_code,
                access_level="owner",
                country=None,
            ),
        ),
        is_superuser=True,
    )


def optional_user_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_BEARER),
    service: AuthService = Depends(get_auth_service),
) -> UserContext | None:
    requested_project_id = request.headers.get("X-Project-ID")
    requested_country = request.headers.get("X-Country")

    if not settings.auth_enabled:
        return build_demo_user_context(request)
    if credentials is None:
        return None

    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token") from exc

    session_key = str(payload.get("sid") or "").strip()
    user_id = str(payload.get("sub") or "").strip()
    if not session_key or not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token payload")

    try:
        service.validate_session(session_key)
        return service.build_user_context(
            user_id,
            requested_project_id=requested_project_id,
            requested_country=requested_country,
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except AuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


def get_current_user_context(ctx: UserContext | None = Depends(optional_user_context)) -> UserContext:
    if ctx is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return ctx


def require_permission(permission: str):
    def _dependency(ctx: UserContext = Depends(get_current_user_context)) -> UserContext:
        try:
            require_permission_check(ctx, permission)
        except AuthorizationError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        return ctx

    return _dependency


def build_request_context(
    request: Request,
    *,
    user: UserContext | None,
    session_id: str | None = None,
    trace_id: str | None = None,
) -> RequestContext:
    return RequestContext(
        request_id=request.headers.get("X-Request-ID") or uuid.uuid4().hex,
        user=user,
        session_id=session_id,
        trace_id=trace_id,
    )
