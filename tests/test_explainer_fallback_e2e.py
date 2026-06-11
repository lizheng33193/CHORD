"""R7 Task 3.3 — Claude 不可达时 ModelClient 自动 fallback 到 Gemini 验证。

验证策略：在 ModelClient 层直接验证（不绕 explainer 复杂构造签名）。
等价性：所有 explainer 内部都是调 ModelClient.generate_structured(...)，
       ModelClient 层 fallback 工作 = explainer 层 fallback 工作。
"""

from __future__ import annotations

import logging

import pytest


def test_model_client_falls_back_to_gemini_when_claude_unavailable(monkeypatch, caplog):
    """vertex 模式 + Claude endpoint 已就绪 + Claude 调用失败 → 自动走 Gemini。"""
    from app.core.config import settings
    from app.core.model_client import ModelClient
    from app.core.providers.base import ProviderUnavailable
    from app.core.providers.claude_maestro_provider import ClaudeMaestroProvider
    from app.core.providers.gemini_provider import GeminiProvider

    # 1) 强制进 vertex 路径（让 _build_default_provider 走 fallback_chain(claude → gemini)）
    monkeypatch.setattr(settings, "model_mode", "vertex", raising=False)

    # 2) 让 Claude endpoint 看起来已就绪（绕开 ClaudeMaestroProvider.__init__ 的 endpoint 检查）
    fake_cfg = {
        "providers": {
            "claude_maestro": {
                "endpoint": "https://maestro.test/v1/chat",
                "model": "claude-opus-4.7",
                "tier": "10x",
            }
        },
        "routes": {"app_profile.explainer": "claude_maestro"},
        "default_provider": "gemini",
    }
    monkeypatch.setattr("app.core.config.get_llm_config", lambda: fake_cfg)
    monkeypatch.setattr(
        "app.core.providers.claude_maestro_provider.get_llm_config",
        lambda: fake_cfg,
    )
    monkeypatch.setenv("MAESTRO_TOKEN", "test-token-stub")

    # 3) Claude 所有调用都抛 ProviderUnavailable
    def _raise_unavailable(*args, **kwargs):
        raise ProviderUnavailable("simulated maestro down")

    monkeypatch.setattr(ClaudeMaestroProvider, "generate_json", _raise_unavailable)

    # 4) Gemini 返回可用结构化结果
    monkeypatch.setattr(
        GeminiProvider,
        "generate_json",
        lambda self, p, response_schema=None, max_output_tokens=None: {
            "summary": "fallback ok",
            "score": 0.5,
        },
    )

    # 5) 调用 ModelClient（默认 vertex 模式 → fallback_chain(claude, gemini)）
    caplog.set_level(logging.WARNING)
    client = ModelClient()
    out = client.generate_structured(
        skill_name="app_profile",
        prompt="test prompt",
        fallback_result={"degraded": True},
        route_key="app_profile.explainer",
    )

    # 6) 断言 fallback 生效
    assert out["status"] == "ok", f"expected ok after fallback, got {out['status']}"
    assert out["structured_result"] == {"summary": "fallback ok", "score": 0.5}, \
        "structured_result should come from Gemini fallback, not Claude"
    # 应该看到 fallback 日志
    assert "provider_fallback" in caplog.text.lower() or "fallback" in caplog.text.lower(), \
        f"expected provider_fallback log, got: {caplog.text}"


def test_model_client_no_fallback_when_claude_succeeds(monkeypatch):
    """Claude 调用成功 → 不触发 fallback，结果直接来自 Claude。"""
    from app.core.config import settings
    from app.core.model_client import ModelClient
    from app.core.providers.claude_maestro_provider import ClaudeMaestroProvider
    from app.core.providers.gemini_provider import GeminiProvider

    monkeypatch.setattr(settings, "model_mode", "vertex", raising=False)
    fake_cfg = {
        "providers": {
            "claude_maestro": {
                "endpoint": "https://maestro.test/v1/chat",
                "model": "claude-opus-4.7",
                "tier": "10x",
            }
        },
        "routes": {"app_profile.explainer": "claude_maestro"},
        "default_provider": "gemini",
    }
    monkeypatch.setattr("app.core.config.get_llm_config", lambda: fake_cfg)
    monkeypatch.setattr(
        "app.core.providers.claude_maestro_provider.get_llm_config",
        lambda: fake_cfg,
    )
    monkeypatch.setenv("MAESTRO_TOKEN", "test-token-stub")

    monkeypatch.setattr(
        ClaudeMaestroProvider,
        "generate_json",
        lambda self, p, response_schema=None, max_output_tokens=None: {
            "summary": "from claude",
            "score": 0.9,
        },
    )

    # Gemini 必须不被调用（如果调到说明 fallback 错误触发）
    def _gemini_must_not_be_called(*args, **kwargs):
        pytest.fail("Gemini should NOT be called when Claude succeeds")

    monkeypatch.setattr(GeminiProvider, "generate_json", _gemini_must_not_be_called)

    client = ModelClient()
    out = client.generate_structured(
        skill_name="app_profile",
        prompt="test prompt",
        fallback_result={"degraded": True},
        route_key="app_profile.explainer",
    )

    assert out["status"] == "ok"
    assert out["structured_result"] == {"summary": "from claude", "score": 0.9}
