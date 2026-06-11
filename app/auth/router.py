"""Auth API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.database import get_db
from app.auth.dependencies import get_current_user_context, get_auth_service
from app.auth.jwt import JWTError, decode_access_token
from app.auth.schemas import (
    LoginRequest,
    LoginResponse,
    MyProjectsResponse,
    PermissionListResponse,
    ProjectScopeResponse,
    RegisterRequest,
    RegisterResponse,
    UserMe,
)
from app.auth.service import AuthService
from app.core.audit import record_audit_event
from app.core.user_context import UserContext


router = APIRouter(prefix="/api/auth", tags=["auth"])
_BEARER = HTTPBearer(auto_error=False)


def _serialize_me(ctx: UserContext) -> UserMe:
    return UserMe(
        id=int(ctx.user_id) if str(ctx.user_id).isdigit() else 0,
        username=ctx.username,
        email=ctx.email or "unknown@example.com",
        display_name=ctx.display_name,
        roles=list(ctx.roles),
        permissions=list(ctx.permissions),
        default_project_id=int(ctx.project_id) if ctx.project_id and str(ctx.project_id).isdigit() else None,
        default_country=ctx.country,
        project_code=ctx.project_code,
        is_superuser=ctx.is_superuser,
    )


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(
    body: RegisterRequest,
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> RegisterResponse:
    try:
        user = service.register_user(
            username=body.username,
            email=str(body.email),
            password=body.password,
            display_name=body.display_name,
            role_codes=body.role_codes,
        )
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    record_audit_event(
        db,
        user_id=user.id,
        project_id=user.default_project_id,
        country=user.default_country,
        event_type="auth.register",
        action="register",
        resource_type="user",
        resource_id=str(user.id),
    )
    db.commit()
    return RegisterResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
    )


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    user = service.authenticate_user(body.username_or_email, body.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username/email or password")

    token, ctx = service.create_login_session(
        user,
        user_agent=request.headers.get("User-Agent"),
        ip_address=request.client.host if request.client is not None else None,
    )
    record_audit_event(
        db,
        user_id=user.id,
        project_id=user.default_project_id,
        country=user.default_country,
        event_type="auth.login",
        action="login",
        resource_type="user",
        resource_id=str(user.id),
    )
    db.commit()
    return LoginResponse(access_token=token, user=_serialize_me(ctx))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    ctx: UserContext = Depends(get_current_user_context),
    credentials: HTTPAuthorizationCredentials | None = Depends(_BEARER),
    service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> Response:
    if credentials is not None:
        try:
            payload = decode_access_token(credentials.credentials)
            sid = str(payload.get("sid") or "").strip()
            if sid:
                service.revoke_session(sid)
        except JWTError:
            pass

    record_audit_event(
        db,
        user_id=int(ctx.user_id) if str(ctx.user_id).isdigit() else None,
        project_id=int(ctx.project_id) if ctx.project_id and str(ctx.project_id).isdigit() else None,
        country=ctx.country,
        event_type="auth.logout",
        action="logout",
        resource_type="user",
        resource_id=ctx.user_id,
        request_id=request.headers.get("X-Request-ID"),
    )
    db.commit()
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserMe)
def me(ctx: UserContext = Depends(get_current_user_context)) -> UserMe:
    return _serialize_me(ctx)


@router.get("/my-permissions", response_model=PermissionListResponse)
def my_permissions(ctx: UserContext = Depends(get_current_user_context)) -> PermissionListResponse:
    return PermissionListResponse(permissions=list(ctx.permissions))


@router.get("/my-projects", response_model=MyProjectsResponse)
def my_projects(ctx: UserContext = Depends(get_current_user_context)) -> MyProjectsResponse:
    return MyProjectsResponse(
        projects=[
            ProjectScopeResponse(
                project_id=int(scope.project_id) if str(scope.project_id).isdigit() else 0,
                project_code=scope.project_code,
                access_level=scope.access_level,
                country=scope.country,
            )
            for scope in ctx.project_scopes
        ]
    )
