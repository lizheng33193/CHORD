"""Permission and scope helpers."""

from __future__ import annotations

from dataclasses import replace

from app.core.user_context import UserContext


def has_permission(ctx: UserContext, permission: str) -> bool:
    if ctx.is_superuser:
        return True
    return permission in ctx.permissions


def require_permission(ctx: UserContext, permission: str) -> None:
    if not has_permission(ctx, permission):
        raise PermissionError(f"missing permission: {permission}")


def has_project_access(ctx: UserContext, project_id: str) -> bool:
    if ctx.is_superuser:
        return True
    return any(scope.project_id == str(project_id) for scope in ctx.project_scopes)


def require_project_access(ctx: UserContext, project_id: str) -> None:
    if not has_project_access(ctx, project_id):
        raise PermissionError(f"no access to project: {project_id}")


def has_country_access(ctx: UserContext, country: str, *, project_id: str | None = None) -> bool:
    if ctx.is_superuser:
        return True
    normalized_country = str(country or "").strip().lower()
    target_project_id = str(project_id or ctx.project_id or "")
    for scope in ctx.project_scopes:
        if target_project_id and scope.project_id != target_project_id:
            continue
        if scope.country is None or scope.country == normalized_country:
            return True
    return False


def require_country_access(ctx: UserContext, country: str, *, project_id: str | None = None) -> None:
    if not has_country_access(ctx, country, project_id=project_id):
        raise PermissionError(f"no access to country: {country}")


def resolve_scope(
    ctx: UserContext,
    *,
    requested_project_id: str | None = None,
    requested_country: str | None = None,
) -> UserContext:
    next_project_id = str(requested_project_id or ctx.project_id or "")
    next_country = (requested_country or ctx.country or None)
    if requested_project_id:
        require_project_access(ctx, next_project_id)
    if next_country:
        require_country_access(ctx, next_country, project_id=next_project_id or ctx.project_id)

    project_code = ctx.project_code
    if next_project_id:
        for scope in ctx.project_scopes:
            if scope.project_id == next_project_id:
                project_code = scope.project_code
                break

    return replace(
        ctx,
        project_id=(next_project_id or None),
        project_code=project_code,
        country=(str(next_country).lower() if next_country else None),
    )
