"""Orchestrator service that coordinates repository access and skill execution."""

from __future__ import annotations

from threading import RLock
from time import perf_counter
from typing import Any

from app.core.config import settings
from app.core.logger import get_logger
from app.core.model_client import ModelClient
from app.repositories.local_repository import LocalUserRepository
from app.repositories.warehouse_repository import WarehouseUserRepository
from app.runtime_skills.base import SkillRegistry
from app.schemas.final_response import AnalyzeResponse, UserAnalysisResult
from app.runtime_skills.app_profile_agent import AppProfileSkill
from app.runtime_skills.behavior_profile_agent import BehaviorProfileSkill
from app.runtime_skills.comprehensive_agent import ComprehensiveProfileSkill
from app.runtime_skills.credit_profile_agent import CreditProfileSkill
from app.runtime_skills.ops_advice_agent import OpsAdviceSkill
from app.runtime_skills.product_advice_agent import ProductAdviceSkill
from app.services.label_builder import build_standardized_labels


logger = get_logger(__name__)


class AnalysisOrchestrator:
    """Execute the multi-skill pipeline via a SkillRegistry.

    Skills are registered with ``stage`` and ``depends_on`` metadata.
    The registry handles parallel execution within a stage and sequential
    ordering across stages.  This design is a drop-in replacement for the
    previous hard-coded ThreadPoolExecutor logic and provides a clean
    extension point for future LangGraph migration.
    """

    def __init__(self, *, strict_data_mode: bool = False) -> None:
        """Initialize repository, model client and skill registry."""
        self.strict_data_mode = strict_data_mode
        self.repository = self._init_repository()
        self.model_client = ModelClient()
        self.registry = self._build_registry()
        self._module_cache: dict[tuple[str, str, str, str], dict] = {}
        self._cache_lock = RLock()

    def _build_registry(self) -> SkillRegistry:
        """Create and populate the skill registry.

        To add a new skill (e.g. ProductAdviceSkill):
            1. Create a class extending ``BaseSkill`` with ``stage=2``
               and ``depends_on=["comprehensive_profile"]``.
            2. Register it here.
        """
        registry = SkillRegistry(max_workers=3)
        registry.register(AppProfileSkill(self.model_client))
        registry.register(BehaviorProfileSkill(self.model_client))
        registry.register(CreditProfileSkill(self.model_client))
        registry.register(ComprehensiveProfileSkill(self.model_client))
        registry.register(ProductAdviceSkill(self.model_client))
        registry.register(OpsAdviceSkill(self.model_client))
        return registry

    def analyze(
        self,
        uids: list[str],
        application_time: str | None = None,
        country_code: str = "mx",
        progress_callback=None,
    ) -> AnalyzeResponse:
        """Analyze every uid and collect profile outputs."""
        results = [
            self._analyze_single_user(
                uid,
                application_time=application_time,
                country_code=country_code,
                progress_callback=progress_callback,
            )
            for uid in uids
        ]
        return AnalyzeResponse(results=results)

    def _analyze_single_user(
        self,
        uid: str,
        application_time: str | None = None,
        country_code: str = "mx",
        progress_callback=None,
    ) -> UserAnalysisResult:
        """Run all registered skills for one user via the registry."""
        logger.info("Start analyze uid=%s", uid)
        started = perf_counter()

        all_results = self.registry.run_all(
            uid=uid,
            progress_callback=progress_callback,
            repository=self.repository,
            application_time=application_time,
            country_code=country_code,
        )

        logger.info("Analyze complete uid=%s duration=%.2fs", uid, perf_counter() - started)

        standardized_labels = build_standardized_labels(
            app_profile=all_results.get("app_profile"),
            behavior_profile=all_results.get("behavior_profile"),
            credit_profile=all_results.get("credit_profile"),
            comprehensive_profile=all_results.get("comprehensive_profile"),
            product_advice=all_results.get("product_advice"),
            ops_advice=all_results.get("ops_advice"),
        )

        user_result = UserAnalysisResult(
            uid=uid,
            app_profile=all_results.get("app_profile", {}),
            behavior_profile=all_results.get("behavior_profile", {}),
            credit_profile=all_results.get("credit_profile", {}),
            comprehensive_profile=all_results.get("comprehensive_profile", {}),
            product_advice=all_results.get("product_advice"),
            ops_advice=all_results.get("ops_advice"),
            standardized_labels=standardized_labels,
        )

        if progress_callback is not None:
            progress_callback({
                "type": "analysis_progress",
                "uid": uid,
                "result": user_result.model_dump(mode="json"),
            })

        return user_result

    def _init_repository(self) -> LocalUserRepository | WarehouseUserRepository:
        """Build repository instance based on data source setting."""
        if settings.data_source == "warehouse":
            logger.info("Using warehouse repository.")
            return WarehouseUserRepository()
        logger.info("Using local repository.")
        return LocalUserRepository(allow_sample_fallback=not self.strict_data_mode)

    # -- Module-level analysis (progressive loading) -----------------------

    SUPPORTED_MODULES = {"app", "behavior", "credit", "comprehensive", "product", "ops"}

    MODULE_SKILL_MAP = {
        "app": "app_profile",
        "behavior": "behavior_profile",
        "credit": "credit_profile",
        "comprehensive": "comprehensive_profile",
        "product": "product_advice",
        "ops": "ops_advice",
    }

    def analyze_module(
        self,
        uid: str,
        module: str,
        application_time: str | None = None,
        country_code: str = "mx",
    ) -> dict:
        """Run one module and return a non-throwing status payload."""
        normalized_uid = str(uid or "").strip()
        normalized_module = str(module or "").strip().lower()
        if not normalized_uid:
            return self._module_error_payload(
                uid=normalized_uid,
                module=normalized_module or "unknown",
                code="invalid_uid",
                message="UID is required.",
            )
        if normalized_module not in self.SUPPORTED_MODULES:
            return self._module_error_payload(
                uid=normalized_uid,
                module=normalized_module or "unknown",
                code="invalid_module",
                message=f"Unsupported module: {normalized_module}",
            )
        if normalized_module == "comprehensive":
            return self._analyze_comprehensive_module(
                normalized_uid,
                application_time=application_time,
                country_code=country_code,
            )
        if normalized_module in ("product", "ops"):
            return self._analyze_advisory_module(
                normalized_uid,
                normalized_module,
                application_time=application_time,
                country_code=country_code,
            )
        return self._run_single_module(
            normalized_uid,
            normalized_module,
            application_time=application_time,
            country_code=country_code,
        )

    def _run_single_module(
        self,
        uid: str,
        module: str,
        application_time: str | None = None,
        country_code: str = "mx",
    ) -> dict:
        """Run an independent module and cache successful payloads."""
        started = perf_counter()
        skill_name = self.MODULE_SKILL_MAP[module]
        skill = self.registry.get(skill_name)
        try:
            kwargs: dict = {
                "uid": uid,
                "repository": self.repository,
                "country_code": country_code,
            }
            if module == "app":
                kwargs["application_time"] = application_time
            result = skill.analyze(**kwargs)
            logger.info(
                "Module done uid=%s module=%s duration=%.2fs",
                uid, module, perf_counter() - started,
            )
            self._set_cached(uid, module, application_time, country_code, result)
            return {"uid": uid, "module": module, "status": "ok", "data": result, "error": None}
        except Exception as exc:
            logger.exception("Module failed uid=%s module=%s: %s", uid, module, exc)
            return self._module_error_payload(
                uid=uid, module=module, code="module_runtime_error", message=str(exc)
            )

    def _analyze_comprehensive_module(
        self,
        uid: str,
        application_time: str | None = None,
        country_code: str = "mx",
    ) -> dict:
        """Run comprehensive from cached or freshly computed upstream modules."""
        upstream: dict[str, dict] = {}
        for mod in ("app", "behavior", "credit"):
            cached = self._get_cached(uid, mod, application_time, country_code)
            if cached is not None:
                upstream[mod] = cached
                continue
            payload = self._run_single_module(
                uid,
                mod,
                application_time=application_time,
                country_code=country_code,
            )
            if payload.get("status") == "ok" and isinstance(payload.get("data"), dict):
                upstream[mod] = payload["data"]
                continue
            return self._module_error_payload(
                uid=uid,
                module="comprehensive",
                code="dependency_module_failed",
                message=f"Dependency module failed: {mod}",
            )
        started = perf_counter()
        try:
            comp_skill = self.registry.get("comprehensive_profile")
            result = comp_skill.analyze(
                uid=uid,
                repository=self.repository,
                country_code=country_code,
                app_profile_result=upstream["app"],
                behavior_profile_result=upstream["behavior"],
                credit_profile_result=upstream["credit"],
            )
            logger.info(
                "Module done uid=%s module=comprehensive duration=%.2fs",
                uid, perf_counter() - started,
            )
            self._set_cached(uid, "comprehensive", application_time, country_code, result)
            return {"uid": uid, "module": "comprehensive", "status": "ok", "data": result, "error": None}
        except Exception as exc:
            logger.exception("Comprehensive module failed uid=%s: %s", uid, exc)
            return self._module_error_payload(
                uid=uid, module="comprehensive", code="module_runtime_error", message=str(exc)
            )

    def _analyze_advisory_module(
        self,
        uid: str,
        module: str,
        application_time: str | None = None,
        country_code: str = "mx",
    ) -> dict:
        """Run a stage-2 advisory module (product/ops) with comprehensive dependency."""
        comp_cached = self._get_cached(uid, "comprehensive", application_time, country_code)
        if comp_cached is None:
            comp_payload = self._analyze_comprehensive_module(
                uid,
                application_time=application_time,
                country_code=country_code,
            )
            if comp_payload.get("status") != "ok":
                return self._module_error_payload(
                    uid=uid, module=module, code="dependency_module_failed",
                    message="Comprehensive module failed",
                )
            comp_cached = comp_payload["data"]
        started = perf_counter()
        skill_name = self.MODULE_SKILL_MAP[module]
        try:
            skill = self.registry.get(skill_name)
            result = skill.analyze(
                uid=uid,
                repository=self.repository,
                country_code=country_code,
                comprehensive_profile_result=comp_cached,
            )
            logger.info(
                "Module done uid=%s module=%s duration=%.2fs",
                uid, module, perf_counter() - started,
            )
            self._set_cached(uid, module, application_time, country_code, result)
            return {"uid": uid, "module": module, "status": "ok", "data": result, "error": None}
        except Exception as exc:
            logger.exception("Advisory module failed uid=%s module=%s: %s", uid, module, exc)
            return self._module_error_payload(
                uid=uid, module=module, code="module_runtime_error", message=str(exc)
            )

    def _cache_key(
        self,
        uid: str,
        module: str,
        application_time: str | None,
        country_code: str,
    ) -> tuple[str, str, str, str]:
        return (uid, module, str(application_time or ""), country_code)

    def _get_cached(
        self,
        uid: str,
        module: str,
        application_time: str | None,
        country_code: str,
    ) -> dict | None:
        with self._cache_lock:
            cached = self._module_cache.get(
                self._cache_key(uid, module, application_time, country_code)
            )
            return dict(cached) if isinstance(cached, dict) else None

    def _set_cached(
        self,
        uid: str,
        module: str,
        application_time: str | None,
        country_code: str,
        result: dict,
    ) -> None:
        with self._cache_lock:
            self._module_cache[
                self._cache_key(uid, module, application_time, country_code)
            ] = dict(result)

    def _module_error_payload(
        self, *, uid: str, module: str, code: str, message: str, details: dict | None = None
    ) -> dict:
        return {
            "uid": uid, "module": module, "status": "error", "data": None,
            "error": {"code": code, "message": message, "details": details or {}},
        }


# -- Shared singleton (all route modules import this) -----------------------
shared_orchestrator = AnalysisOrchestrator()
