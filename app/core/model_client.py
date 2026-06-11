"""Model client Facade — delegates to LLMProvider implementations.

Phase 2: __init__ accepts optional provider injection; generate_structured
delegates the real LLM call to self._provider.generate_json. JSON repair,
google-genai transport, and parse_success / transport_success logging now
live in app/core/providers/gemini_provider.py + json_repair.py. This module
keeps only Facade concerns: mock short-circuit, error classification on the
except path, and the payload_ready log emitted after a successful generate.
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.core.config import settings
from app.core.logger import get_logger
from app.core.providers.base import LLMProvider


logger = get_logger(__name__)


def _build_default_provider(mode: str) -> LLMProvider:
    if mode == "mock":
        from app.core.providers.mock_provider import MockProvider
        return MockProvider()
    if mode in {"gemini", "vertex", "vertexai", "gemini-vertex"}:
        # 2026-05-05 hotfix: 走 factory 而不是直接 GeminiProvider(mode=mode)，
        # 这样 default provider 也会读 config.yaml::llm.providers.gemini.model（默认
        # gemini-2.5-flash），而不是 silent 沿用 .env::MODEL_NAME。
        # 修前 .env=gemini-3.1-pro-preview 时 run_profile 会卡 10+ 分钟。
        from app.core.providers.factory import build_provider_by_name
        gemini = build_provider_by_name("gemini")
        # R4 P0-C: vertex 模式且 Plan #02 已完成（claude_maestro endpoint 真实回填）时，
        # 自动包装 fallback_chain(claude → gemini)。
        # try-import 隔离：Plan #01 单跑时 ClaudeMaestroProvider 文件不存在也不影响。
        if mode in {"vertex", "vertexai", "gemini-vertex"}:
            try:
                from app.core.providers.claude_maestro_provider import ClaudeMaestroProvider
                from app.core.config import get_llm_config
                from app.core.providers.base import fallback_chain
                cfg = get_llm_config()
                ep = cfg.get("providers", {}).get("claude_maestro", {}).get("endpoint", "")
                if ep and ep != "[Spike Pending]":
                    claude = ClaudeMaestroProvider()
                    return fallback_chain(
                        claude, gemini,
                        on_fallback=lambda f, t, e: logger.warning(
                            "provider_fallback %s→%s: %s", f, t, e
                        ),
                    )
            except Exception:
                pass
        return gemini
    raise ValueError(f"Unsupported MODEL_MODE={mode}")


class ModelClient:
    """Encapsulate model invocation so skills stay provider-agnostic."""

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.mode = settings.model_mode
        self.model_name = settings.resolved_model_name
        self.api_key = settings.resolved_gemini_api_key
        self.vertex_project_id = settings.vertex_project_id
        self.vertex_location = settings.vertex_location
        self.credentials_path = settings.resolved_google_application_credentials
        if self.credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.credentials_path
        self._provider = provider or _build_default_provider(self.mode)
        # R5: 提前初始化避免 Phase 3 _record_usage 调用前 AttributeError。
        # Plan #03 Phase 2 budget 模块直接读 self.last_token_usage["total"]。
        self.last_token_usage: dict[str, int] = {"prompt": 0, "completion": 0, "total": 0}

    def generate_structured(
        self,
        skill_name: str,
        prompt: str,
        fallback_result: dict[str, Any],
        response_schema: dict[str, Any] | None = None,
        *,
        route_key: str | None = None,
    ) -> dict[str, Any]:
        """Return structured model output with graceful fallback."""
        if self.mode == "mock":
            logger.info("ModelClient mock mode for skill=%s route=%s", skill_name, route_key)
            return {
                "status": "ok",
                "structured_result": fallback_result,
                "model_name": self.model_name,
                "prompt_preview": prompt[:200],
            }

        try:
            # Plan #02 Task 1.3: provider 解析块（route_key 提供时按 config.yaml routes 切换）。
            # 必须在 try 块内：build_provider_by_name 实例化 ClaudeMaestroProvider 在
            # endpoint=[Spike Pending] 时会抛 ProviderUnavailable，应被 except 接住走
            # fallback degraded path，而不是冒泡到 explainer/skill。
            # P2-1（性能）：Phase 1 不做 provider cache，避免引入并发安全问题。
            #
            # 2026-05-04 hotfix：route 重定向若失败（如 claude_maestro Spike Pending），
            # 自动回退到 self._provider（vertex 模式下是 gemini 链），保证 LLM 调用
            # 真实落地，不再无端走 degraded fallback。
            provider = self._provider
            if route_key is not None:
                from app.core.config import llm_provider_for
                from app.core.providers.factory import build_provider_by_name
                target_name = llm_provider_for(route_key)
                if target_name != provider.provider_name:
                    try:
                        provider = build_provider_by_name(target_name)
                    except Exception as build_exc:
                        logger.warning(
                            "route %s target=%s unavailable (%s); fallback to %s",
                            route_key, target_name, build_exc, provider.provider_name,
                        )

            structured_result = provider.generate_json(prompt, response_schema=response_schema)
            self._log_payload_ready(skill_name, structured_result)
            # R5 (Plan #01 Phase 3 Task 3.3): record token usage on success path only
            # (mock / except paths do not call to avoid polluting per-session budget).
            # Plan #03 Phase 2 budget module reads self.last_token_usage["total"].
            self._record_usage(prompt, json.dumps(structured_result, ensure_ascii=False))
            return {
                "status": "ok",
                "structured_result": structured_result,
                "model_name": self.model_name,
                "prompt_preview": prompt[:200],
            }
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Model unavailable for skill=%s: %s", skill_name, exc)
            degraded = dict(fallback_result)
            degraded["status"] = (
                degraded.get("status")
                if degraded.get("status") == "data_missing"
                else "model_unavailable"
            )
            degraded["model_error"] = self._classify_model_error(exc)
            return {
                "status": "model_unavailable",
                "structured_result": degraded,
                "model_name": self.model_name,
                "prompt_preview": prompt[:200],
            }

    def _classify_model_error(self, exc: Exception) -> str:
        message = str(exc)
        lowered = message.lower()
        if "blocked" in lowered:
            return f"blocked: {message}"
        if "candidates were empty" in lowered or "did not include text content" in lowered:
            return f"empty_response: {message}"
        if "json_repair_failed" in lowered:
            return f"json_repair_failed: {message}"
        if "schema_validation_failed" in lowered:
            return f"schema_validation_failed: {message}"
        if "invalid \\u" in lowered or "unterminated string" in lowered:
            return f"json_parse: {message}"
        if "invalid control character" in lowered:
            return f"json_parse: {message}"
        if "jsondecodeerror" in lowered:
            return f"json_parse: {message}"
        if "expecting value" in lowered or "expecting ',' delimiter" in lowered:
            return f"json_parse: {message}"
        if "expecting ':' delimiter" in lowered:
            return f"json_parse: {message}"
        if "extra data" in lowered:
            return f"json_parse: {message}"
        return message

    def _record_usage(self, prompt: str, completion: str) -> None:
        prompt_tokens = self._provider.count_tokens(prompt)
        completion_tokens = self._provider.count_tokens(completion)
        self.last_token_usage = {
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": prompt_tokens + completion_tokens,
        }

    def _log_payload_ready(self, skill_name: str, payload: dict[str, Any]) -> None:
        logger.info(
            "LLM payload ready skill=%s model=%s key_count=%s",
            skill_name,
            self.model_name,
            len(payload),
        )

    # ---------------------------------------------------------------
    # Backward-compat shims for legacy private API probed by baseline
    # tests/test_model_client_repair.py + test_model_client_unescaped_newlines.py.
    # Phase 2 [TDD red->green] migration moved real impl to
    # app/core/providers/json_repair.py. These shims preserve test
    # contract without modifying tests/. Plan #03 / Step 8 may reclaim
    # by migrating tests to json_repair module-level functions.
    # ---------------------------------------------------------------

    def _parse_json_text(self, response_text: str) -> dict[str, Any]:
        """Backward-compat shim — forwards to app.core.providers.json_repair.parse_json_text.

        Kept only for tests/test_model_client_repair.py and
        tests/test_model_client_unescaped_newlines.py which probe the legacy
        private API. New code should import from json_repair directly.

        TODO(Step 8 audit): migrate baseline tests to json_repair module
        functions and delete this shim.
        """
        from app.core.providers.json_repair import parse_json_text
        return parse_json_text(response_text)

    @staticmethod
    def _truncate_to_balanced_json(text: str) -> str | None:
        """Backward-compat shim — forwards to app.core.providers.json_repair._truncate_to_balanced_json.

        Kept only for tests/test_model_client_repair.py probing
        ModelClient._truncate_to_balanced_json as a class-level staticmethod.
        New code should import from json_repair directly.

        TODO(Step 8 audit): migrate baseline tests to json_repair module
        functions and delete this shim.
        """
        from app.core.providers.json_repair import _truncate_to_balanced_json
        return _truncate_to_balanced_json(text)

    def _repair_json_candidate(self, candidate: str, exc) -> str:
        """Backward-compat shim — forwards to app.core.providers.json_repair._repair_json_candidate.

        Kept only for tests/test_model_client_repair.py which probes the legacy
        private API. New code should import from json_repair directly.

        TODO(Step 8 audit): migrate baseline tests to json_repair module
        functions and delete this shim.
        """
        from app.core.providers.json_repair import _repair_json_candidate
        return _repair_json_candidate(candidate, exc)
