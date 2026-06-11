"""Password hashing utilities."""

from __future__ import annotations

from passlib.context import CryptContext


_PWD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(raw_password: str) -> str:
    return _PWD_CONTEXT.hash(raw_password)


def verify_password(raw_password: str, password_hash: str) -> bool:
    return _PWD_CONTEXT.verify(raw_password, password_hash)
