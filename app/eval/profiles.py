"""Profile registry for the shared eval foundation."""

from __future__ import annotations

from app.eval.schemas import EvalProfile


_PROFILES: dict[str, EvalProfile] = {
    "pr_acceptance": EvalProfile(
        profile_id="pr_acceptance",
        suites=["release_gate_smoke"],
        description="Non-blocking PR acceptance smoke over shared eval foundation.",
        strict_by_default=False,
    ),
    "production_release": EvalProfile(
        profile_id="production_release",
        suites=["release_gate_smoke"],
        description="Strict production-release smoke over shared eval foundation.",
        strict_by_default=True,
    ),
}


def get_profile(profile_id: str) -> EvalProfile:
    try:
        return _PROFILES[profile_id]
    except KeyError as exc:
        raise KeyError(f"unknown eval profile: {profile_id}") from exc


def list_profiles() -> list[EvalProfile]:
    return list(_PROFILES.values())
