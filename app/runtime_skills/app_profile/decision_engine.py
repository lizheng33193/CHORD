"""Decision engine layer for the App profile pipeline."""

from __future__ import annotations

from app.runtime_skills.app_profile.contracts import (
    AppDecisionResult,
    AppFeatureBundle,
    AppRunContext,
)
from app.scripts.app_profile_payload_builder import (
    build_app_decision_result,
    build_app_prompt_payload,
)


class AppDecisionEngine:
    """Build deterministic decisions from App features."""

    def decide(
        self,
        feature_bundle: AppFeatureBundle,
        _context: AppRunContext,
    ) -> AppDecisionResult:
        return build_app_decision_result(feature_bundle)

    def build_prompt_payload(
        self,
        feature_bundle: AppFeatureBundle,
        decision_result: AppDecisionResult,
    ) -> dict:
        return build_app_prompt_payload(feature_bundle, decision_result)
