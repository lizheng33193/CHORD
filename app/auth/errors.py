"""Typed auth errors used to separate authentication from authorization."""

from __future__ import annotations


class AuthError(PermissionError):
    """Base auth-domain permission error."""


class AuthenticationError(AuthError):
    """Raised when authentication or session validation fails."""


class AuthorizationError(AuthError):
    """Raised when a user is authenticated but not allowed."""
