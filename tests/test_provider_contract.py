"""Provider接口契约测试 — 确保所有Provider 遵循 LLMProvider Protocol。"""

from __future__ import annotations

import pytest

from app.core.providers import LLMProvider, ProviderUnavailable
from app.core.providers.mock_provider import MockProvider
from app.core.providers.gemini_provider import GeminiProvider


@pytest.fixture(params=["mock", "gemini"])
def provider(request) -> LLMProvider:
    if request.param == "mock":
        return MockProvider()
    return GeminiProvider(mode="gemini")


def test_provider_implements_protocol(provider: LLMProvider) -> None:
    assert isinstance(provider, LLMProvider)
    assert provider.provider_name in {"mock", "gemini"}


def test_provider_capability_shape(provider: LLMProvider) -> None:
    cap = provider.capability
    assert isinstance(cap.supports_streaming, bool)
    assert isinstance(cap.supports_json_mode, bool)
    assert isinstance(cap.max_context_tokens, int)
    assert cap.max_context_tokens > 0
    assert isinstance(cap.supports_tools, bool)


def test_provider_count_tokens_returns_positive(provider: LLMProvider) -> None:
    assert provider.count_tokens("hello world") >= 1


def test_mock_provider_generate_json_returns_canned() -> None:
    p = MockProvider()
    out = p.generate_json("prompt", response_schema=None)
    assert out["_mock"] is True


def test_gemini_provider_unavailable_when_credentials_missing(monkeypatch) -> None:
    """Phase 2 后契约：凭证缺失时 GeminiProvider 抛 ProviderUnavailable。

    Note: Settings.resolved_gemini_api_key is a pydantic-settings property
    (no setter/deleter), so monkeypatch.setattr on the settings module path
    silently fails (Plan's `raising=False` would mask the AttributeError).
    Patch the constructed instance attribute directly — same semantic
    ("credentials missing"), reliable in any environment.
    """
    from app.core.providers.gemini_provider import GeminiProvider
    from app.core.providers.base import ProviderUnavailable
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    p = GeminiProvider(mode="gemini")
    monkeypatch.setattr(p, "api_key", "", raising=False)
    with pytest.raises(ProviderUnavailable):
        p.generate_json("prompt")
