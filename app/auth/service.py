"""Auth service orchestration."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth.errors import AuthenticationError
from app.auth.jwt import create_access_token, hash_token
from app.auth.models import Permission, Project, Role, RolePermission, User, UserProjectAccess, UserRole, UserSession
from app.auth.password import hash_password, verify_password
from app.auth.permissions import normalize_country_scope_value, resolve_scope
from app.auth.seed import DEFAULT_PROJECT_CODE
from app.core.config import settings
from app.core.user_context import ProjectAccessScope, UserContext


SELF_SERVICE_ROLE_ALLOWLIST = {"analyst", "viewer"}


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def register_user(
        self,
        *,
        username: str,
        email: str,
        password: str,
        display_name: str | None = None,
        role_codes: list[str] | None = None,
        default_country: str = "mx",
        allow_privileged_roles: bool = False,
    ) -> User:
        normalized_username = username.strip()
        normalized_email = email.strip().lower()
        if self.db.scalar(select(User).where(User.username == normalized_username)) is not None:
            raise ValueError("username already exists")
        if self.db.scalar(select(User).where(User.email == normalized_email)) is not None:
            raise ValueError("email already exists")

        normalized_roles = [str(code or "").strip().lower() for code in (role_codes or []) if str(code or "").strip()]
        if not normalized_roles:
            normalized_roles = [settings.auth_default_register_role]
        if not allow_privileged_roles:
            disallowed = [code for code in normalized_roles if code not in SELF_SERVICE_ROLE_ALLOWLIST]
            if disallowed:
                raise PermissionError(f"self-service registration cannot assign roles: {', '.join(disallowed)}")

        project = self._get_default_project()
        user = User(
            username=normalized_username,
            email=normalized_email,
            password_hash=hash_password(password),
            display_name=display_name,
            status="active",
            is_superuser=False,
            default_project_id=project.id,
            default_country=normalize_country_scope_value(default_country or "mx") or "mx",
        )
        self.db.add(user)
        self.db.flush()

        for role_code in normalized_roles:
            role = self._get_role(role_code)
            self.db.add(UserRole(user_id=user.id, role_id=role.id))

        self.db.add(
            UserProjectAccess(
                user_id=user.id,
                project_id=project.id,
                country=normalize_country_scope_value(default_country or "mx") or "mx",
                access_level="member",
            )
        )
        self.db.commit()
        self.db.refresh(user)
        return user

    def authenticate_user(self, username_or_email: str, password: str) -> User | None:
        identity = str(username_or_email or "").strip()
        if not identity:
            return None
        user = self.db.scalar(
            select(User).where(
                or_(User.username == identity, User.email == identity.lower())
            )
        )
        if user is None or user.status != "active":
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    def create_login_session(
        self,
        user: User,
        *,
        user_agent: str | None = None,
        ip_address: str | None = None,
        requested_project_id: str | None = None,
        requested_country: str | None = None,
    ) -> tuple[str, UserContext]:
        ctx = self.build_user_context(user.id, requested_project_id=requested_project_id, requested_country=requested_country)
        session_key = uuid.uuid4().hex
        token = create_access_token(
            sub=str(user.id),
            sid=session_key,
            project_id=ctx.project_id,
            country=ctx.country,
            expires_delta=timedelta(minutes=settings.auth_jwt_expire_minutes),
        )
        expires_at = datetime.utcnow() + timedelta(minutes=settings.auth_jwt_expire_minutes)
        self.db.add(
            UserSession(
                user_id=user.id,
                session_key=session_key,
                session_token_hash=hash_token(token),
                user_agent=user_agent,
                ip_address=ip_address,
                expires_at=expires_at,
            )
        )
        user.last_login_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(user)
        return token, ctx

    def validate_session(self, session_key: str) -> UserSession:
        session = self.db.scalar(select(UserSession).where(UserSession.session_key == session_key))
        if session is None:
            raise AuthenticationError("session not found")
        if session.revoked_at is not None:
            raise AuthenticationError("session revoked")
        if session.expires_at <= datetime.utcnow():
            raise AuthenticationError("session expired")
        return session

    def revoke_session(self, session_key: str) -> None:
        session = self.db.scalar(select(UserSession).where(UserSession.session_key == session_key))
        if session is None or session.revoked_at is not None:
            return
        session.revoked_at = datetime.utcnow()
        self.db.commit()

    def get_user_by_id(self, user_id: int | str) -> User | None:
        stmt = self._user_context_query().where(User.id == int(user_id))
        return self.db.scalar(stmt)

    def get_user_permissions(self, user_id: int | str) -> list[str]:
        return list(self.build_user_context(user_id).permissions)

    def get_user_projects(self, user_id: int | str) -> list[ProjectAccessScope]:
        return list(self.build_user_context(user_id).project_scopes)

    def build_user_context(
        self,
        user_id: int | str,
        *,
        requested_project_id: str | None = None,
        requested_country: str | None = None,
    ) -> UserContext:
        user = self.get_user_by_id(user_id)
        if user is None or user.status != "active":
            raise AuthenticationError("user not found or inactive")

        roles = sorted({
            link.role.code
            for link in user.role_links
            if link.role is not None
        })
        if user.is_superuser:
            permissions = sorted({
                permission.code
                for permission in self.db.scalars(select(Permission)).all()
            })
        else:
            permissions = sorted({
                link.permission.code
                for role_link in user.role_links
                if role_link.role is not None
                for link in role_link.role.permission_links
                if link.permission is not None
            })

        project_scopes = tuple(
            ProjectAccessScope(
                project_id=str(link.project_id),
                project_code=link.project.code if link.project is not None else DEFAULT_PROJECT_CODE,
                access_level=link.access_level,
                country=normalize_country_scope_value(link.country) or None,
            )
            for link in user.project_links
        )

        default_project = user.default_project
        fallback_scope = project_scopes[0] if project_scopes else None
        project_id = str(user.default_project_id) if user.default_project_id is not None else (fallback_scope.project_id if fallback_scope else None)
        project_code = default_project.code if default_project is not None else (fallback_scope.project_code if fallback_scope else None)
        country = normalize_country_scope_value(
            user.default_country or (fallback_scope.country if fallback_scope else None) or settings.auth_demo_country
        ) or "mx"

        ctx = UserContext(
            user_id=str(user.id),
            username=user.username,
            email=user.email,
            display_name=user.display_name,
            roles=tuple(roles),
            permissions=tuple(permissions),
            project_id=project_id,
            project_code=project_code,
            country=country,
            project_scopes=project_scopes,
            is_superuser=user.is_superuser,
        )
        return resolve_scope(
            ctx,
            requested_project_id=(str(requested_project_id) if requested_project_id is not None else None),
            requested_country=requested_country,
        )

    def _get_default_project(self) -> Project:
        project = self.db.scalar(select(Project).where(Project.code == DEFAULT_PROJECT_CODE))
        if project is None:
            project = self.db.scalar(select(Project).limit(1))
        if project is None:
            raise RuntimeError("auth project seed missing")
        return project

    def _get_role(self, role_code: str) -> Role:
        role = self.db.scalar(select(Role).where(Role.code == role_code))
        if role is None:
            raise ValueError(f"unknown role: {role_code}")
        return role

    def _user_context_query(self):
        return select(User).options(
            selectinload(User.default_project),
            selectinload(User.role_links).selectinload(UserRole.role).selectinload(Role.permission_links).selectinload(RolePermission.permission),
            selectinload(User.project_links).selectinload(UserProjectAccess.project),
        )
