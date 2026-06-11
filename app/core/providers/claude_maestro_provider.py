"""Claude Opus 4.7 via Agent Maestro — production impl."""

from __future__ import annotations

import os
from typing import Any, Iterator

import httpx

from app.core.config import get_llm_config
from app.core.logger import get_logger
from app.core.providers.base import LLMProvider, ProviderCapability, ProviderUnavailable
from app.core.providers.json_repair import parse_json_text, RETRYABLE_PARSE_HINTS

logger = get_logger(__name__)

_REQUEST_TIMEOUT_SECONDS = 30


class ClaudeMaestroProvider(LLMProvider):
    """Real impl: HTTP POST -> Maestro endpoint, parse tool_use payload.

    R7 P1-4 协议假设警示：本类的 _post / generate_json 实装基于对 Maestro
    response shape 的纸面假设（content[].type=='tool_use'.input /
    content[].type=='text'.text）。Plan #03 Phase 0 Task 0.2 Maestro Spike
    完成后必须按真实 response shape 重新审视全部代码（字段名 / 结构 /
    错误码 / 鉴权 header 差异都可能要改）。
    """

    def __init__(self) -> None:
        cfg = get_llm_config().get("providers", {}).get("claude_maestro", {})
        self.endpoint = cfg.get("endpoint", "")
        self.model = cfg.get("model", "claude-opus-4.7")
        self.tier = cfg.get("tier", "10x")
        self.token = os.environ.get("MAESTRO_TOKEN", "")
        if not self.endpoint or self.endpoint == "[Spike Pending]":
            raise ProviderUnavailable(
                "ClaudeMaestroProvider: endpoint missing or [Spike Pending]; complete Plan #03 Phase 0 Spike first"
            )
        if not self.token:
            raise ProviderUnavailable(
                "ClaudeMaestroProvider: MAESTRO_TOKEN env var missing"
            )

    @property
    def provider_name(self) -> str:
        return "claude_maestro"

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            supports_streaming=True,
            supports_json_mode=True,
            max_context_tokens=1_000_000,
            supports_tools=True,
        )

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
                resp = client.post(
                    self.endpoint,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ProviderUnavailable(f"maestro transport: {exc}") from exc
        if resp.status_code >= 500 or resp.status_code == 408:
            raise ProviderUnavailable(f"maestro {resp.status_code}: {resp.text[:200]}")
        if resp.status_code >= 400:
            raise ValueError(f"maestro client error {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    def generate_json(
        self,
        prompt: str,
        response_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "tier": self.tier,
            "messages": [{"role": "user", "content": prompt}],
            "tool_choice": {"type": "json_object"},
        }
        if max_output_tokens:
            payload["max_tokens"] = max_output_tokens
        if response_schema:
            payload["response_schema"] = response_schema

        body = self._post(payload)
        for item in body.get("content", []):
            if item.get("type") == "tool_use" and isinstance(item.get("input"), dict):
                logger.info("maestro tool_use ok model=%s", self.model)
                return item["input"]
        text = ""
        for item in body.get("content", []):
            if item.get("type") == "text" and item.get("text"):
                text += str(item["text"])
        if not text:
            raise ValueError("Model response candidates were empty")
        try:
            return parse_json_text(text)
        except Exception as exc:
            if any(h in str(exc) for h in RETRYABLE_PARSE_HINTS):
                payload["messages"][0]["content"] = (
                    prompt + "\n\nRespond with ONLY a valid JSON object. No prose."
                )
                body2 = self._post(payload)
                text2 = "".join(
                    str(i.get("text", "")) for i in body2.get("content", []) if i.get("type") == "text"
                )
                return parse_json_text(text2)
            raise

    def generate_text(
        self,
        prompt: str,
        max_output_tokens: int | None = None,
    ) -> str:
        payload = {
            "model": self.model,
            "tier": self.tier,
            "messages": [{"role": "user", "content": prompt}],
        }
        if max_output_tokens:
            payload["max_tokens"] = max_output_tokens
        body = self._post(payload)
        return "".join(
            str(i.get("text", "")) for i in body.get("content", []) if i.get("type") == "text"
        )

    def stream(self, prompt: str) -> Iterator[str]:
        # V1 简化：不使用原生 SSE，一次调用后 yield 整个文本。Plan #03 SSE 上层自己拆分。
        yield self.generate_text(prompt)

    def count_tokens(self, text: str) -> int:
        # Maestro 暂未提供 count_tokens API；naive 估算，后续可接入 anthropic tokenizer。
        return max(1, len(text) // 4)
