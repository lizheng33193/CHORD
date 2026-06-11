"""Feature builder layer for the App profile pipeline."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logger import get_logger
from app.runtime_skills.app_profile.contracts import AppFeatureBundle, AppRawData, AppRunContext
from app.runtime_skills.app_profile.category_llm_classifier import AppCategoryLLMClassifier
from app.scripts.app_profile_payload_builder import build_app_feature_bundle


logger = get_logger(__name__)


class AppFeatureBuilder:
    """Build deterministic App features from raw repository data."""

    def __init__(self, model_client: Any | None = None) -> None:
        self.model_client = model_client
        self._classifier: AppCategoryLLMClassifier | None = None
        if model_client is not None:
            try:
                self._classifier = AppCategoryLLMClassifier(
                    model_client=model_client,
                    prompt_path=settings.resolve_path(
                        f"{settings.prompt_dir}/app_category_classifier_prompt.md"
                    ),
                    cache_path=settings.resolve_path(
                        "outputs/cache/app_category_cache.json"
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("AppCategoryLLMClassifier init failed: %s", exc)
                self._classifier = None

    def build(self, raw_data: AppRawData, context: AppRunContext) -> AppFeatureBundle:
        raw_app_data = {
            "uid": raw_data["uid"],
            "source_file": raw_data["source_meta"].get("origin_ref", ""),
            "apps": raw_data.get("records", []),
        }
        return build_app_feature_bundle(
            raw_data["uid"],
            raw_app_data,
            context.get("application_time"),
            country_code=context["country_code"],
            classifier=self._classifier,
        )
