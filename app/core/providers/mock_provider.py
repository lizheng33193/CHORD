"""Mock provider for tests and local-no-credential development."""

from __future__ import annotations

from typing import Any, Iterator

from app.core.providers.base import LLMProvider, ProviderCapability


class MockProvider(LLMProvider):
    """Returns canned fallback results, never touches the network."""

    def __init__(self, model_name: str = "mock-model") -> None:
        self._model_name = model_name

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            supports_streaming=False,
            supports_json_mode=True,
            max_context_tokens=100_000,
            supports_tools=False,
        )

    def generate_json(
        self,
        prompt: str,
        response_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        return {"_mock": True, "prompt_preview": prompt[:200]}

    def generate_text(
        self,
        prompt: str,
        max_output_tokens: int | None = None,
    ) -> str:
        return f"[mock] {prompt[:200]}"

    def stream(self, prompt: str) -> Iterator[str]:
        yield f"[mock] {prompt[:200]}"

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)
