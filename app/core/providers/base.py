"""LLMProvider Protocol and shared capability metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterator, Protocol, runtime_checkable


@dataclass(frozen=True)
class ProviderCapability:
    """Provider feature flags consumed by routing decisions."""

    supports_streaming: bool
    supports_json_mode: bool
    max_context_tokens: int
    supports_tools: bool


class ProviderUnavailable(Exception):
    """Raised when a Provider cannot serve the call (network / auth / quota)."""


@runtime_checkable
class LLMProvider(Protocol):
    """Provider-agnostic LLM interface."""

    @property
    def provider_name(self) -> str: ...

    @property
    def capability(self) -> ProviderCapability: ...

    def generate_json(
        self,
        prompt: str,
        response_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]: ...

    def generate_text(
        self,
        prompt: str,
        max_output_tokens: int | None = None,
    ) -> str: ...

    def stream(self, prompt: str) -> Iterator[str]: ...

    def count_tokens(self, text: str) -> int: ...


def fallback_chain(
    primary: LLMProvider,
    secondary: LLMProvider,
    *,
    on_fallback: Callable[[str, str, Exception], None] | None = None,
) -> LLMProvider:
    """Wrap primary with automatic fallback to secondary on ProviderUnavailable."""
    class _ChainedProvider(LLMProvider):
        @property
        def provider_name(self) -> str:
            return primary.provider_name

        @property
        def capability(self) -> ProviderCapability:
            return primary.capability

        def generate_json(self, prompt, response_schema=None, max_output_tokens=None):
            try:
                return primary.generate_json(prompt, response_schema, max_output_tokens)
            except ProviderUnavailable as exc:
                if on_fallback:
                    on_fallback(primary.provider_name, secondary.provider_name, exc)
                return secondary.generate_json(prompt, response_schema, max_output_tokens)

        def generate_text(self, prompt, max_output_tokens=None):
            try:
                return primary.generate_text(prompt, max_output_tokens)
            except ProviderUnavailable:
                return secondary.generate_text(prompt, max_output_tokens)

        def stream(self, prompt):
            try:
                yield from primary.stream(prompt)
            except ProviderUnavailable:
                yield from secondary.stream(prompt)

        def count_tokens(self, text):
            return primary.count_tokens(text)

    return _ChainedProvider()
