"""Pydantic schemas for auth APIs."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str | None = Field(None, max_length=128)
    role_codes: list[str] | None = None


class RegisterResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    display_name: str | None = None


class LoginRequest(BaseModel):
    username_or_email: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)


class UserMe(BaseModel):
    id: int
    username: str
    email: EmailStr
    display_name: str | None = None
    roles: list[str]
    permissions: list[str]
    default_project_id: int | None = None
    default_country: str | None = None
    project_code: str | None = None
    is_superuser: bool = False


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserMe


class PermissionListResponse(BaseModel):
    permissions: list[str]


class ProjectScopeResponse(BaseModel):
    project_id: int
    project_code: str
    access_level: str
    country: str | None = None


class MyProjectsResponse(BaseModel):
    projects: list[ProjectScopeResponse]
