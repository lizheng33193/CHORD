"""JWT helpers for auth access tokens."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.core.config import settings


ALGORITHM = "HS256"


def create_access_token(*, sub: str, sid: str, project_id: str | None, country: str | None, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.auth_jwt_expire_minutes))
    payload = {
        "sub": sub,
        "sid": sid,
        "project_id": project_id,
        "country": country,
        "exp": expire,
    }
    return jwt.encode(payload, settings.auth_jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.auth_jwt_secret, algorithms=[ALGORITHM])


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


__all__ = ["JWTError", "create_access_token", "decode_access_token", "hash_token"]
