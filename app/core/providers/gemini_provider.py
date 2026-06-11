"""Gemini / Vertex provider — Phase 2 real impl migrated from model_client.py.

Baseline behavior preserved 1:1:
- Two transport modes (api-key Gemini + Vertex AI) via single class
- Tenacity-based single retry on RETRYABLE_PARSE_HINTS
- 4 _log_parse_success emit points: response.parsed direct hit (gemini),
  response.parsed direct hit (vertex), parse_json_text main success,
  parse_json_text truncate-balanced fallback success
- block_reason → "Model response blocked: <reason>" elevation
- naive count_tokens fallback when google-genai count_tokens unavailable
"""

from __future__ import annotations

import os
import re as _re
from typing import Any, Iterator

from tenacity import (
    retry,
    retry_if_exception_message,
    stop_after_attempt,
    wait_fixed,
)

from app.core.config import settings
from app.core.logger import get_logger
from app.core.providers.base import LLMProvider, ProviderCapability, ProviderUnavailable
from app.core.providers.json_repair import RETRYABLE_PARSE_HINTS, parse_json_text


logger = get_logger(__name__)


class GeminiProvider(LLMProvider):
    """Gemini API key mode + Vertex AI mode wrapped behind LLMProvider."""

    def __init__(self, mode: str = "gemini", model_name: str | None = None) -> None:
        if mode not in {"gemini", "vertex", "vertexai", "gemini-vertex"}:
            raise ValueError(f"GeminiProvider unsupported mode={mode}")
        self.mode = mode
        # 2026-05-05 model_name override：factory 可传入锁定模型（如 trace 锁 gemini-2.5-flash 避免 pro-preview 循环 bug）
        # 传 None 则走 settings.resolved_model_name（.env / config.yaml 免同）
        self.model_name = model_name or settings.resolved_model_name
        self.api_key = settings.resolved_gemini_api_key
        self.vertex_project_id = settings.vertex_project_id
        self.vertex_location = settings.vertex_location
        creds = settings.resolved_google_application_credentials
        if creds:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            supports_streaming=True,
            supports_json_mode=True,
            max_context_tokens=1_000_000,
            supports_tools=True,
        )

    def _provider_label(self) -> str:
        """Distinguish vertex vs gemini for logging — preserves baseline log shape."""
        return "vertex" if self.mode in {"vertex", "vertexai", "gemini-vertex"} else "gemini"

    def _emit_parse_success(self, payload: dict[str, Any], *, parsed_direct: bool) -> None:
        """Single emit point for 'LLM JSON parsed' log — covers all 4 baseline call sites."""
        logger.info(
            "LLM JSON parsed provider=%s model=%s keys=%s direct=%s",
            self._provider_label(),
            self.model_name,
            ",".join(sorted(str(key) for key in payload.keys())[:12]),
            parsed_direct,
        )

    def _build_client(self):
        try:
            from google import genai
        except Exception as exc:  # pylint: disable=broad-except
            raise ImportError(
                "google-genai is not installed; add it to requirements before using MODEL_MODE=gemini/vertex"
            ) from exc

        if self.mode == "gemini":
            if not self.api_key:
                raise ProviderUnavailable("GEMINI_API_KEY is missing")
            client = genai.Client(api_key=self.api_key)
            logger.info("LLM transport success provider=gemini model=%s", self.model_name)
            return client

        # vertex / vertexai / gemini-vertex
        if not self.vertex_project_id:
            raise ProviderUnavailable("VERTEX_PROJECT_ID is missing for MODEL_MODE=vertex")
        if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            raise ProviderUnavailable(
                "GOOGLE_APPLICATION_CREDENTIALS is missing; point it to your service account key.json"
            )
        client = genai.Client(
            vertexai=True,
            project=self.vertex_project_id,
            location=self.vertex_location,
        )
        logger.info(
            "LLM transport success provider=vertex model=%s project=%s location=%s",
            self.model_name,
            self.vertex_project_id,
            self.vertex_location,
        )
        return client

    def _build_config(self, response_schema, max_output_tokens):
        from google.genai import types
        config_kwargs: dict[str, Any] = {
            "response_mime_type": "application/json",
            "temperature": 0,
        }
        resolved = max_output_tokens if max_output_tokens is not None else settings.model_max_output_tokens
        if resolved:
            config_kwargs["max_output_tokens"] = resolved
        if response_schema:
            config_kwargs["response_json_schema"] = response_schema
        config_cls = getattr(types, "GenerateContentConfig", None)
        if not config_cls:
            return config_kwargs
        try:
            return config_cls(**config_kwargs)
        except TypeError as exc:
            message = str(exc)
            if "max_output_tokens" in message and "unexpected" in message.lower():
                cleaned = dict(config_kwargs)
                cleaned.pop("max_output_tokens", None)
                return config_cls(**cleaned)
            raise

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(0.5),
        retry=retry_if_exception_message(
            match="|".join(_re.escape(h) for h in RETRYABLE_PARSE_HINTS)
        ),
        reraise=True,
    )
    def generate_json(
        self,
        prompt: str,
        response_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        try:
            client = self._build_client()
            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=self._build_config(response_schema, max_output_tokens),
            )
            parsed = getattr(response, "parsed", None)
            if isinstance(parsed, dict):
                self._emit_parse_success(parsed, parsed_direct=True)
                return parsed
            if hasattr(response, "text") and response.text:
                payload = parse_json_text(str(response.text))
            else:
                payload = parse_json_text(self._extract_text_from_response(response))
            self._emit_parse_success(payload, parsed_direct=False)
            return payload
        except ProviderUnavailable:
            raise
        except Exception as exc:
            message = str(exc)
            if any(hint in message for hint in RETRYABLE_PARSE_HINTS):
                logger.warning("gemini retryable parse error: %s", message)
                raise
            logger.warning("gemini call failed mode=%s: %s", self.mode, message)
            raise ProviderUnavailable(message) from exc

    def generate_text(
        self,
        prompt: str,
        max_output_tokens: int | None = None,
    ) -> str:
        try:
            client = self._build_client()
            from google.genai import types
            config_cls = getattr(types, "GenerateContentConfig", None)
            cfg_kwargs: dict[str, Any] = {"temperature": 0}
            if max_output_tokens:
                cfg_kwargs["max_output_tokens"] = max_output_tokens
            cfg = config_cls(**cfg_kwargs) if config_cls else cfg_kwargs
            response = client.models.generate_content(
                model=self.model_name, contents=prompt, config=cfg,
            )
            text = getattr(response, "text", None)
            if text:
                return str(text)
            return self._extract_text_from_response(response)
        except ProviderUnavailable:
            raise
        except Exception as exc:
            raise ProviderUnavailable(str(exc)) from exc

    def stream(self, prompt: str) -> Iterator[str]:
        # Phase 2 不实装 streaming（baseline model_client 也未启用），保留显式契约。
        # Plan #03 之后如启用 SSE，再覆盖此方法。
        raise ProviderUnavailable("GeminiProvider.stream not implemented")

    def count_tokens(self, text: str) -> int:
        # google-genai 提供 client.models.count_tokens；失败退回 naive 估算。
        try:
            client = self._build_client()
            resp = client.models.count_tokens(model=self.model_name, contents=text)
            total = getattr(resp, "total_tokens", None)
            if total:
                return int(total)
            return max(1, len(text) // 4)
        except Exception:
            return max(1, len(text) // 4)

    def _extract_text_from_response(self, response: Any) -> str:
        """Extract text from a google-genai response or raise a useful error.

        Preserves baseline block_reason elevation: when candidates parse fails
        AND prompt_feedback.block_reason exists, raise as
        'Model response blocked: <reason>' (non-retryable).
        """
        candidates = getattr(response, "candidates", None)
        try:
            return self._extract_text_from_candidates(candidates)
        except Exception as exc:  # pylint: disable=broad-except
            prompt_feedback = getattr(response, "prompt_feedback", None)
            block_reason = getattr(prompt_feedback, "block_reason", None) if prompt_feedback else None
            if block_reason:
                raise ValueError(f"Model response blocked: {block_reason}") from exc
            raise

    def _extract_text_from_candidates(self, candidates: Any) -> str:
        if not candidates:
            raise ValueError("Model response candidates were empty")
        text_parts: list[str] = []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                text = getattr(part, "text", None)
                if text:
                    text_parts.append(str(text))
        if not text_parts:
            raise ValueError("Model response candidates were empty")
        return "\n".join(text_parts)
