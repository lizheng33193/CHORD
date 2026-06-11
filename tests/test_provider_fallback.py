"""Verify fallback_chain switches to secondary on ProviderUnavailable."""

from __future__ import annotations

from typing import Iterator

from app.core.providers.base import (
    LLMProvider,
    ProviderCapability,
    ProviderUnavailable,
    fallback_chain,
)


class _FailingProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "failing"

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(False, True, 1024, False)

    def generate_json(self, prompt, response_schema=None, max_output_tokens=None):
        raise ProviderUnavailable("test")

    def generate_text(self, prompt, max_output_tokens=None):
        raise ProviderUnavailable("test")

    def stream(self, prompt: str) -> Iterator[str]:
        raise ProviderUnavailable("test")

    def count_tokens(self, text: str) -> int:
        return len(text)


class _OkProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "ok"

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(False, True, 1024, False)

    def generate_json(self, prompt, response_schema=None, max_output_tokens=None):
        return {"ok": True}

    def generate_text(self, prompt, max_output_tokens=None):
        return "ok"

    def stream(self, prompt: str) -> Iterator[str]:
        yield "ok"

    def count_tokens(self, text: str) -> int:
        return len(text)


def test_fallback_chain_switches_on_unavailable() -> None:
    chained = fallback_chain(_FailingProvider(), _OkProvider())
    assert chained.generate_json("p") == {"ok": True}


def test_fallback_chain_records_event() -> None:
    events: list[tuple[str, str]] = []
    chained = fallback_chain(
        _FailingProvider(),
        _OkProvider(),
        on_fallback=lambda f, t, e: events.append((f, t)),
    )
    chained.generate_json("p")
    assert events == [("failing", "ok")]
