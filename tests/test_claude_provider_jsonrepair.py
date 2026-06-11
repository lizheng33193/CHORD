"""Claude Maestro Provider 契约测试。

测试用 monkeypatch 替换 _post，不真连任何外部 endpoint。
"""

from __future__ import annotations

import pytest

from app.core.providers.base import ProviderUnavailable


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("MAESTRO_TOKEN", "test-token-stub")
    fake_cfg = {
        "providers": {
            "claude_maestro": {
                "endpoint": "https://maestro.test/v1/chat",
                "model": "claude-opus-4.7",
                "tier": "10x",
            }
        }
    }
    # Patch both the source module and the provider's local binding (the provider
    # imports get_llm_config at module load time, so patching only app.core.config
    # leaves the provider's local reference untouched).
    monkeypatch.setattr("app.core.config.get_llm_config", lambda: fake_cfg)
    monkeypatch.setattr(
        "app.core.providers.claude_maestro_provider.get_llm_config",
        lambda: fake_cfg,
    )
    from app.core.providers.claude_maestro_provider import ClaudeMaestroProvider
    return ClaudeMaestroProvider()


class _FakeResponse:
    def __init__(self, status_code: int, body: dict | str):
        self.status_code = status_code
        self._body = body
        self.text = body if isinstance(body, str) else ""

    def json(self):
        return self._body


def test_claude_provider_happy_path(provider, monkeypatch):
    captured = {}

    def _fake_post(self, payload):
        captured["payload"] = payload
        return {"content": [{"type": "tool_use", "input": {"score": 0.8, "label": "low_risk"}}]}

    monkeypatch.setattr(provider, "_post", _fake_post.__get__(provider))
    out = provider.generate_json("hello prompt")
    assert out == {"score": 0.8, "label": "low_risk"}
    assert captured["payload"]["model"] == "claude-opus-4.7"


def test_claude_provider_repair_unescaped_newline(provider, monkeypatch):
    raw = '{"text":"line1\nline2"}'  # bare newline inside string

    def _fake_post(self, payload):
        return {"content": [{"type": "text", "text": raw}]}

    monkeypatch.setattr(provider, "_post", _fake_post.__get__(provider))
    out = provider.generate_json("p")
    assert out == {"text": "line1\nline2"}


def test_claude_provider_truncated_triggers_retry(provider, monkeypatch):
    calls = {"n": 0}

    def _fake_post(self, payload):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"content": [{"type": "text", "text": '{"a": "unter'}]}  # truncated
        return {"content": [{"type": "text", "text": '{"a": "ok"}'}]}

    monkeypatch.setattr(provider, "_post", _fake_post.__get__(provider))
    out = provider.generate_json("p")
    assert out == {"a": "ok"}
    assert calls["n"] == 2


def test_claude_provider_endpoint_unreachable_raises_unavailable(provider, monkeypatch):
    """Transport-level ConnectError inside _post must be converted to ProviderUnavailable.

    Patches httpx.Client.post (one layer below _post) so the real _post try/except
    branch does the conversion. Patching _post itself would bypass the conversion logic.
    """
    import httpx

    class _ExplodingClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            raise httpx.ConnectError("dns failure")

    monkeypatch.setattr(
        "app.core.providers.claude_maestro_provider.httpx.Client",
        _ExplodingClient,
    )
    with pytest.raises(ProviderUnavailable):
        provider.generate_json("p")


def test_claude_provider_count_tokens_returns_positive(provider):
    assert provider.count_tokens("hello world") >= 1
