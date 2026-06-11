"""Runtime identity context shared across API and harness boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProjectAccessScope:
    project_id: str
    project_code: str
    access_level: str
    country: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_code": self.project_code,
            "access_level": self.access_level,
            "country": self.country,
        }


@dataclass(frozen=True)
class UserContext:
    user_id: str
    username: str
    email: str | None
    display_name: str | None
    roles: tuple[str, ...]
    permissions: tuple[str, ...]
    project_id: str | None
    project_code: str | None
    country: str | None
    project_scopes: tuple[ProjectAccessScope, ...]
    is_superuser: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "display_name": self.display_name,
            "roles": list(self.roles),
            "permissions": list(self.permissions),
            "project_id": self.project_id,
            "project_code": self.project_code,
            "country": self.country,
            "project_scopes": [scope.to_dict() for scope in self.project_scopes],
            "is_superuser": self.is_superuser,
        }
