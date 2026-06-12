"""Permission and scope helpers."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from app.auth.errors import AuthorizationError
from app.core.user_context import UserContext


_COUNTRY_SCOPE_ALIASES: dict[str, str] = {
    "mx": "mx",
    "mexico": "mx",
    "th": "th",
    "thailand": "th",
}


def normalize_country_scope_value(country: str | None) -> str:
    normalized = str(country or "").strip().lower()
    if not normalized:
        return ""
    return _COUNTRY_SCOPE_ALIASES.get(normalized, normalized)


def has_permission(ctx: UserContext, permission: str) -> bool:
    if ctx.is_superuser:
        return True
    return permission in ctx.permissions


def require_permission(ctx: UserContext, permission: str) -> None:
    if not has_permission(ctx, permission):
        raise AuthorizationError(f"missing permission: {permission}")


def require_permissions(ctx: UserContext, permissions: Iterable[str]) -> None:
    missing = [permission for permission in permissions if not has_permission(ctx, permission)]
    if missing:
        raise AuthorizationError(f"missing permission: {', '.join(missing)}")


def has_project_access(ctx: UserContext, project_id: str) -> bool:
    if ctx.is_superuser:
        return True
    return any(scope.project_id == str(project_id) for scope in ctx.project_scopes)


def require_project_access(ctx: UserContext, project_id: str) -> None:
    if not has_project_access(ctx, project_id):
        raise AuthorizationError(f"no access to project: {project_id}")


def has_country_access(ctx: UserContext, country: str, *, project_id: str | None = None) -> bool:
    if ctx.is_superuser:
        return True
    normalized_country = normalize_country_scope_value(country)
    target_project_id = str(project_id or ctx.project_id or "")
    for scope in ctx.project_scopes:
        if target_project_id and scope.project_id != target_project_id:
            continue
        scope_country = normalize_country_scope_value(scope.country)
        if scope.country is None or scope_country == normalized_country:
            return True
    return False


def require_country_access(ctx: UserContext, country: str, *, project_id: str | None = None) -> None:
    if not has_country_access(ctx, country, project_id=project_id):
        raise AuthorizationError(f"no access to country: {normalize_country_scope_value(country) or country}")


def resolve_scope(
    ctx: UserContext,
    *,
    requested_project_id: str | None = None,
    requested_country: str | None = None,
) -> UserContext:
    next_project_id = str(requested_project_id or ctx.project_id or "")
    next_country = normalize_country_scope_value(requested_country or ctx.country or None) or None
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
        country=next_country,
    )
