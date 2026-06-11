"""Verify ModelClient Facade preserves backward-compatible behavior."""

from __future__ import annotations

from typing import Any, Iterator

import pytest

from app.core.model_client import ModelClient
from app.core.providers.base import LLMProvider, ProviderCapability


class _FakeProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "fake"

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            supports_streaming=False,
            supports_json_mode=True,
            max_context_tokens=8192,
            supports_tools=False,
        )

    def generate_json(self, prompt, response_schema=None, max_output_tokens=None):
        return {"echo": prompt[:50]}

    def generate_text(self, prompt, max_output_tokens=None):
        return prompt[:50]

    def stream(self, prompt: str) -> Iterator[str]:
        yield prompt[:50]

    def count_tokens(self, text: str) -> int:
        return len(text)


def test_model_client_accepts_injected_provider() -> None:
    client = ModelClient(provider=_FakeProvider())
    out = client.generate_structured(
        skill_name="test_skill",
        prompt="hello world",
        fallback_result={"fallback": True},
    )
    assert out["status"] == "ok"
    assert out["structured_result"] == {"echo": "hello world"}
    assert "model_name" in out
    assert "prompt_preview" in out


def test_model_client_default_mock_mode(monkeypatch) -> None:
    """Verify mock mode short-circuits without invoking provider.

    R5 fixup: Settings.model_mode is a class attribute evaluated at module
    import time (pydantic-settings + dotenv behavior), so monkeypatch.setenv
    + Settings() does not pick up new env. Patch settings.model_mode directly
    on the singleton imported by model_client to exercise the mock branch.
    """
    monkeypatch.setattr("app.core.model_client.settings.model_mode", "mock")
    client = ModelClient()
    out = client.generate_structured("s", "p", {})
    assert out["status"] == "ok"
