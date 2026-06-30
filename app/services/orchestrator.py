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
from app.services.orchestrator_agent.schemas import RunProfileInput, RunProfileOutput
from app.services.profile_dag import ProfileDagExecutor
from app.services.profile_dag.adapters import (
    profile_event_to_legacy_skill_events,
    snapshot_to_module_response,
    snapshot_to_run_profile_rows,
    snapshot_to_user_analysis_result,
)
from app.services.profile_dag.node_registry import PROFILE_NODE_SPECS


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
        self.profile_dag = ProfileDagExecutor(
            node_specs=PROFILE_NODE_SPECS,
            skill_map={name: self.registry.get(name) for name in self.registry.list_all()},
            cache_get=self._get_cached,
            cache_set=self._set_cached,
        )

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
        run, snapshots = self.profile_dag.run(
            uids=uids,
            requested_modules=list(self.SUPPORTED_MODULES),
            application_time=application_time,
            country_code=country_code,
            strict_data_mode=self.strict_data_mode,
            source="api_analyze_stream" if progress_callback is not None else "api_analyze",
            repository=self.repository,
            progress_callback=self._build_analyze_progress_bridge(progress_callback),
        )
        _ = run
        results = [
            self._snapshot_to_user_result(snapshot, progress_callback=progress_callback)
            for snapshot in snapshots
        ]
        return AnalyzeResponse(results=results)

    def _snapshot_to_user_result(
        self,
        snapshot,
        *,
        progress_callback=None,
    ) -> UserAnalysisResult:
        started = perf_counter()
        standardized_labels = build_standardized_labels(
            app_profile=snapshot.module_outputs.get("app"),
            behavior_profile=snapshot.module_outputs.get("behavior"),
            credit_profile=snapshot.module_outputs.get("credit"),
            comprehensive_profile=snapshot.module_outputs.get("comprehensive"),
            product_advice=snapshot.module_outputs.get("product"),
            ops_advice=snapshot.module_outputs.get("ops"),
        )
        user_result = snapshot_to_user_analysis_result(
            snapshot,
            standardized_labels=standardized_labels,
        )
        logger.info("Analyze complete uid=%s duration=%.2fs", snapshot.uid, perf_counter() - started)
        if progress_callback is not None:
            progress_callback({
                "type": "analysis_progress",
                "uid": snapshot.uid,
                "result": user_result.model_dump(mode="json"),
            })
        return user_result

    def _build_analyze_progress_bridge(self, progress_callback):
        if progress_callback is None:
            return None

        def _bridge(event: dict[str, Any]) -> None:
            progress_callback(event)
            for legacy_event in profile_event_to_legacy_skill_events(event):
                progress_callback(legacy_event)

        return _bridge

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
        _, snapshots = self.profile_dag.run(
            uids=[normalized_uid],
            requested_modules=[normalized_module],
            application_time=application_time,
            country_code=country_code,
            strict_data_mode=self.strict_data_mode,
            source="internal",
            repository=self.repository,
        )
        return snapshot_to_module_response(snapshots[0], normalized_module)

    def run_profile_request(
        self,
        input_data: RunProfileInput,
        *,
        progress_callback=None,
    ) -> RunProfileOutput:
        _, snapshots = self.profile_dag.run(
            uids=list(input_data.uids),
            requested_modules=list(input_data.modules or ["app"]),
            application_time=input_data.app_time,
            country_code="mx",
            strict_data_mode=input_data.strict_data_mode,
            source="chat_run_profile",
            repository=self.repository,
            progress_callback=progress_callback,
        )
        rows: list[dict[str, Any]] = []
        cache_hits = 0
        cache_misses = 0
        for snapshot in snapshots:
            rows.extend(snapshot_to_run_profile_rows(snapshot))
            cache_hits += snapshot.cache_hits
            cache_misses += snapshot.cache_misses
        return RunProfileOutput(
            results=rows,
            cache_hits=cache_hits,
            cache_misses=cache_misses,
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
