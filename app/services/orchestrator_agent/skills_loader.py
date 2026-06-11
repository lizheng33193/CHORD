"""load_skill — knowledge layer for country-specific analysis rules."""

from __future__ import annotations

from app.core.config import settings


_SUPPORTED = {"th", "mx", "co", "pe", "cl", "br"}


def load_skill(country: str) -> str:
    """Load country-specific skills md content.

    Raises:
        ValueError: country not in 6 supported codes.
        FileNotFoundError: skills md missing on disk.
    """
    if country not in _SUPPORTED:
        raise ValueError(
            f"Unsupported country code: {country!r}. "
            f"Supported: {sorted(_SUPPORTED)}"
        )
    path = settings.project_root / "docs" / "skills" / "orchestrator" / f"{country}.md"
    if not path.exists():
        raise FileNotFoundError(f"Skills file not found: {path}")
    return path.read_text(encoding="utf-8")
