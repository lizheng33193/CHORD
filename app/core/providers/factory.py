"""Build providers by name from config.yaml."""

from __future__ import annotations

from app.core.providers.base import LLMProvider
from app.core.providers.mock_provider import MockProvider
from app.core.providers.gemini_provider import GeminiProvider


def build_provider_by_name(name: str) -> LLMProvider:
    if name == "mock":
        return MockProvider()
    if name == "gemini":
        from app.core.config import settings, get_llm_config
        # R4 P2-2: 不硬编码 mode，跟 settings.model_mode 走（vertex/gemini/vertexai 任选）
        m = settings.model_mode
        if m not in {"gemini", "vertex", "vertexai", "gemini-vertex"}:
            m = "vertex"
        # 2026-05-05 hotfix: 读 config.yaml::llm.providers.gemini.model，让 config.yaml
        # 成为 explainer 模型选择的单一事实源。否则 .env::MODEL_NAME 一旦被改成
        # 已知有 bug 的模型（如 gemini-3.1-pro-preview infinite repetition），
        # 7 个画像 explainer route 全部 silent 受牵连，run_profile 会卡 10+ 分钟。
        # 读不到时才 fallback 到 settings.resolved_model_name（.env / GEMINI_MODEL）。
        model = (
            get_llm_config()
            .get("providers", {})
            .get("gemini", {})
            .get("model")
        )
        return GeminiProvider(mode=m, model_name=model)
    if name == "gemini_flash":
        # 2026-05-05 为 trace_analyzer 专门锁定 gemini-2.5-flash（避免 pro-preview infinite repetition）
        # 其他 explainer 走默认 settings.model_name（.env 可调）。
        from app.core.config import settings
        m = settings.model_mode
        if m not in {"gemini", "vertex", "vertexai", "gemini-vertex"}:
            m = "vertex"
        return GeminiProvider(mode=m, model_name="gemini-2.5-flash")
    if name == "claude_maestro":
        # Phase 1 stub — Provider 待 Plan #03 Spike 后实装
        from app.core.providers.claude_maestro_provider import ClaudeMaestroProvider
        return ClaudeMaestroProvider()
    raise ValueError(f"Unknown provider name: {name}")
