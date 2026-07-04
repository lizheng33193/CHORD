from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _default_auth_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep non-auth tests on the historical auth-off baseline by default.

    Auth-focused tests can still opt in by monkeypatching ``settings.auth_enabled``
    back to ``True`` inside their own fixtures.
    """

    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", False, raising=False)
    monkeypatch.setattr(settings, "auth_seed_on_startup", False, raising=False)
