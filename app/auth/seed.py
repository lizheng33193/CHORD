"""Seed helpers for auth foundation."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import Permission, Project, Role, RolePermission, User, UserProjectAccess, UserRole
from app.auth.password import hash_password
from app.core.config import settings


DEFAULT_PROJECT_CODE = "maps_lz"

DEFAULT_PERMISSIONS: dict[str, tuple[str, str]] = {
    "profile:run": ("Run profiles", "Run user profiling flows"),
    "profile:view": ("View profiles", "View existing profile outputs"),
    "trace:run": ("Run trace", "Run trace analysis"),
    "trace:view": ("View trace", "View trace results"),
    "data:query:generate": ("Generate SQL", "Generate SQL previews"),
    "data:query:review": ("Review SQL", "Review or approve generated SQL"),
    "data:query:execute": ("Execute SQL", "Execute approved SQL"),
    "data:query:view_sql": ("View SQL", "View generated SQL text"),
    "memory:read": ("Read memory", "Read long-term memory"),
    "memory:write": ("Write memory", "Write long-term memory"),
    "memory:manage": ("Manage memory", "Update or archive long-term memory"),
    "audit:view": ("View audit", "View audit events"),
    "user:manage": ("Manage users", "Manage users and roles"),
    "project:manage": ("Manage projects", "Manage projects and access"),
}

DEFAULT_ROLES: dict[str, tuple[str, str]] = {
    "admin": ("System Admin", "Manage users, permissions, projects, and all runtime actions"),
    "data_admin": ("Data Admin", "Generate, review, and execute SQL"),
    "analyst": ("Analyst", "Run profiles, orchestrator, trace, and memory write"),
    "viewer": ("Viewer", "Read-only viewer for profile outputs and trace results"),
}

ROLE_PERMISSION_MAP: dict[str, tuple[str, ...]] = {
    "admin": tuple(DEFAULT_PERMISSIONS.keys()),
    "data_admin": (
        "profile:run",
        "profile:view",
        "trace:run",
        "trace:view",
        "data:query:generate",
        "data:query:view_sql",
        "data:query:review",
        "data:query:execute",
        "memory:read",
        "memory:write",
        "audit:view",
    ),
    "analyst": (
        "profile:run",
        "profile:view",
        "trace:run",
        "trace:view",
        "data:query:generate",
        "data:query:view_sql",
        "memory:read",
        "memory:write",
    ),
    "viewer": (
        "profile:view",
        "trace:view",
        "memory:read",
    ),
}


def seed_auth_data(db: Session) -> None:
    permission_by_code: dict[str, Permission] = {}
    for code, (name, description) in DEFAULT_PERMISSIONS.items():
        permission = db.scalar(select(Permission).where(Permission.code == code))
        if permission is None:
            permission = Permission(code=code, name=name, description=description)
            db.add(permission)
            db.flush()
        permission_by_code[code] = permission

    role_by_code: dict[str, Role] = {}
    for code, (name, description) in DEFAULT_ROLES.items():
        role = db.scalar(select(Role).where(Role.code == code))
        if role is None:
            role = Role(code=code, name=name, description=description)
            db.add(role)
            db.flush()
        role_by_code[code] = role

    for role_code, permission_codes in ROLE_PERMISSION_MAP.items():
        role = role_by_code[role_code]
        existing_codes = {
            link.permission.code
            for link in role.permission_links
            if link.permission is not None
        }
        for permission_code in permission_codes:
            if permission_code in existing_codes:
                continue
            db.add(RolePermission(role_id=role.id, permission_id=permission_by_code[permission_code].id))
        db.flush()

    project = db.scalar(select(Project).where(Project.code == DEFAULT_PROJECT_CODE))
    if project is None:
        project = Project(code=DEFAULT_PROJECT_CODE, name="MAPS-LZ", description="MAPS-LZ primary harness project")
        db.add(project)
        db.flush()

    admin = db.scalar(select(User).where(User.username == settings.default_admin_username))
    if admin is None:
        admin = db.scalar(select(User).where(User.email == settings.default_admin_email))
    if admin is None:
        admin = User(
            username=settings.default_admin_username,
            email=settings.default_admin_email,
            password_hash=hash_password(settings.default_admin_password),
            display_name="System Admin",
            status="active",
            is_superuser=True,
            default_project_id=project.id,
            default_country="mx",
        )
        db.add(admin)
        db.flush()
    else:
        admin.is_superuser = True
        admin.default_project_id = admin.default_project_id or project.id
        admin.default_country = admin.default_country or "mx"

    admin_role = role_by_code["admin"]
    admin_role_link = db.scalar(
        select(UserRole).where(UserRole.user_id == admin.id, UserRole.role_id == admin_role.id)
    )
    if admin_role_link is None:
        db.add(UserRole(user_id=admin.id, role_id=admin_role.id))

    access = db.scalar(
        select(UserProjectAccess).where(
            UserProjectAccess.user_id == admin.id,
            UserProjectAccess.project_id == project.id,
            UserProjectAccess.country.is_(None),
        )
    )
    if access is None:
        db.add(UserProjectAccess(user_id=admin.id, project_id=project.id, country=None, access_level="owner"))

    db.commit()
