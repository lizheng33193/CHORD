"""Base skill interface and registry for pluggable profile skills.

Every profile skill must subclass ``BaseSkill`` and implement ``analyze()``.
The ``SkillRegistry`` provides dynamic registration, dependency-aware
multi-stage scheduling, and a clean extension point for future LangGraph
migration.

Usage::

    registry = SkillRegistry()
    registry.register(AppProfileSkill(model_client))
    registry.register(BehaviorProfileSkill(model_client))
    results = registry.run_all(uid="123", repository=repo)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from typing import Any

from app.core.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Base Skill
# ---------------------------------------------------------------------------

class BaseSkill(ABC):
    """Contract that every profile skill must implement.

    Attributes:
        name: unique identifier used as dict key in results, e.g. ``"app_profile"``.
        stage: execution stage (lower runs first). Skills in the same stage
               run in parallel; the next stage starts only after the current
               one completes. Default stages:
                 0 — independent data skills (App / Behavior / Credit)
                 1 — fusion skills (Comprehensive)
                 2 — downstream advisory skills (Product Agent / Ops Agent)
        depends_on: names of skills whose outputs are required as keyword
                    arguments to ``analyze()``.
    """

    name: str = ""
    stage: int = 0
    depends_on: list[str] = []

    @abstractmethod
    def analyze(self, uid: str, **kwargs: Any) -> dict[str, Any]:
        """Run the skill for one user and return an ``AgentOutput``-shaped dict.

        Parameters
        ----------
        uid:
            18-digit user identifier.
        **kwargs:
            Injected by the registry.  Guaranteed keys:
            - ``repository`` — a ``BaseUserRepository`` instance (stage-0 skills).
            - ``application_time`` — optional ISO datetime string.
            - ``<skill_name>_result`` — output of a dependency skill (stage ≥1).
        """


# ---------------------------------------------------------------------------
# Skill Registry
# ---------------------------------------------------------------------------

class SkillRegistry:
    """Register skills and execute them in dependency order.

    Designed as the single place to swap in LangGraph later — replace
    ``run_all`` internals with a ``StateGraph`` while keeping the same
    public API.
    """

    def __init__(self, max_workers: int = 3) -> None:
        self._skills: dict[str, BaseSkill] = {}
        self._max_workers = max_workers

    # -- registration -------------------------------------------------------

    def register(self, skill: BaseSkill) -> None:
        """Add a skill.  Raises if ``skill.name`` is already taken."""
        if skill.name in self._skills:
            raise ValueError(f"Skill '{skill.name}' already registered")
        self._skills[skill.name] = skill
        logger.debug("Skill registered: %s (stage=%d)", skill.name, skill.stage)

    def get(self, name: str) -> BaseSkill:
        return self._skills[name]

    def list_all(self) -> list[str]:
        return list(self._skills.keys())

    # -- execution ----------------------------------------------------------

    def run_all(
        self,
        uid: str,
        progress_callback=None,
        **kwargs: Any,
    ) -> dict[str, dict[str, Any]]:
        """Execute every registered skill respecting stage order.

        Skills in the same stage run in parallel.  Each skill's output is
        stored under ``results[skill.name]`` and injected as
        ``<skill.name>_result`` into subsequent stages.

        Parameters
        ----------
        progress_callback:
            Optional ``Callable[[dict], None]``.  When provided, invoked
            before/after each skill with one of three event dicts:
            ``skill_started`` / ``skill_completed`` / ``skill_failed``.
            When ``None`` the registry behaves identically to pre-callback
            semantics — used by the synchronous ``/api/analyze`` path.

        Returns
        -------
        dict mapping skill name → AgentOutput dict.
        """
        results: dict[str, dict[str, Any]] = {}
        stages = sorted({s.stage for s in self._skills.values()})

        for stage in stages:
            stage_skills = [s for s in self._skills.values() if s.stage == stage]

            def _run_skill(skill: BaseSkill) -> tuple[str, dict[str, Any]]:
                t0 = perf_counter()
                if progress_callback is not None:
                    progress_callback({
                        "type": "skill_started",
                        "uid": uid,
                        "skill": skill.name,
                        "stage": stage,
                    })
                # Build kwargs: base kwargs + upstream results as <name>_result
                skill_kwargs = dict(kwargs)
                for dep in skill.depends_on:
                    skill_kwargs[f"{dep}_result"] = results.get(dep, {})
                try:
                    result = skill.analyze(uid=uid, **skill_kwargs)
                except Exception as exc:
                    if progress_callback is not None:
                        progress_callback({
                            "type": "skill_failed",
                            "uid": uid,
                            "skill": skill.name,
                            "stage": stage,
                            "error_message": str(exc),
                            "duration_ms": int((perf_counter() - t0) * 1000),
                        })
                    raise
                duration_ms = int((perf_counter() - t0) * 1000)
                if progress_callback is not None:
                    progress_callback({
                        "type": "skill_completed",
                        "uid": uid,
                        "skill": skill.name,
                        "stage": stage,
                        "duration_ms": duration_ms,
                    })
                logger.info(
                    "Skill done uid=%s skill=%s stage=%d duration=%.2fs",
                    uid, skill.name, stage, duration_ms / 1000.0,
                )
                return skill.name, result

            if len(stage_skills) == 1:
                try:
                    name, result = _run_skill(stage_skills[0])
                    results[name] = result
                except Exception:
                    # Failure already surfaced via skill_failed callback;
                    # downstream skills receive {} fallback via results.get(dep, {}).
                    pass
            else:
                with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
                    futures = [pool.submit(_run_skill, s) for s in stage_skills]
                    for f in futures:
                        try:
                            name, result = f.result()
                            results[name] = result
                        except Exception:
                            pass

        return results
