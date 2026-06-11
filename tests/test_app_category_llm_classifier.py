"""Tests for AppCategoryLLMClassifier."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from app.runtime_skills.app_profile.category_llm_classifier import (
    ALLOWED_CATEGORIES,
    AppCategoryLLMClassifier,
)


_PROMPT_PATH = Path("app/prompts/app_category_classifier_prompt.md")


def _mk_client(mode: str = "vertex", payload: dict | None = None, status: str = "ok"):
    client = MagicMock()
    client.mode = mode
    client.model_name = "gemini-3.1-pro-preview"
    client.generate_structured.return_value = {
        "status": status,
        "structured_result": payload if payload is not None else {},
        "model_name": "gemini-3.1-pro-preview",
        "prompt_preview": "...",
    }
    return client


class TestAppCategoryLLMClassifier:
    def test_mock_mode_returns_none_and_skips_llm(self, tmp_path: Path) -> None:
        client = _mk_client(mode="mock")
        clf = AppCategoryLLMClassifier(client, _PROMPT_PATH, tmp_path / "c.json")
        assert clf.classify(
            app_name="UnknownApp", package_name="com.unknown.app",
            ai_category="", gp_category="",
        ) is None
        client.generate_structured.assert_not_called()

    def test_cache_hit_skips_llm(self, tmp_path: Path) -> None:
        cache_file = tmp_path / "c.json"
        cache_file.write_text(
            json.dumps({"someapp|com.some.app": {"category": "银行金融"}}, ensure_ascii=False),
            encoding="utf-8",
        )
        client = _mk_client(payload={"category": "借贷竞争"})
        clf = AppCategoryLLMClassifier(client, _PROMPT_PATH, cache_file)
        result = clf.classify(
            app_name="SomeApp", package_name="com.some.app",
            ai_category="", gp_category="",
        )
        assert result == "银行金融"
        client.generate_structured.assert_not_called()

    def test_llm_ok_writes_cache(self, tmp_path: Path) -> None:
        cache_file = tmp_path / "c.json"
        client = _mk_client(payload={"category": "借贷竞争", "confidence": 0.92, "reasoning": "现金贷"})
        clf = AppCategoryLLMClassifier(client, _PROMPT_PATH, cache_file)
        result = clf.classify(
            app_name="Cashly", package_name="com.cashly.lend",
            ai_category="finance", gp_category="finance",
        )
        assert result == "借贷竞争"
        client.generate_structured.assert_called_once()
        assert cache_file.exists()
        on_disk = json.loads(cache_file.read_text(encoding="utf-8"))
        assert on_disk["cashly|com.cashly.lend"]["category"] == "借贷竞争"
        assert on_disk["cashly|com.cashly.lend"]["confidence"] == 0.92

    def test_llm_low_confidence_treated_as_miss(self, tmp_path: Path) -> None:
        """Below threshold confidence → dropped, no positive cache entry written."""
        cache_file = tmp_path / "c.json"
        client = _mk_client(payload={"category": "银行金融", "confidence": 0.4})
        clf = AppCategoryLLMClassifier(client, _PROMPT_PATH, cache_file)
        result = clf.classify(
            app_name="WeakSignalApp", package_name="com.weak.signal",
            ai_category="", gp_category="",
        )
        assert result is None
        # 不应中快照 “银行金融” 进去
        if cache_file.exists():
            entry = json.loads(cache_file.read_text(encoding="utf-8")).get("weaksignalapp|com.weak.signal", {})
            assert entry.get("category", "") == ""

    def test_llm_missing_confidence_treated_as_miss(self, tmp_path: Path) -> None:
        """Payload 中缺 confidence 字段 → 默认 0 → 当 miss 处理。"""
        client = _mk_client(payload={"category": "银行金融"})
        clf = AppCategoryLLMClassifier(client, _PROMPT_PATH, tmp_path / "c.json")
        result = clf.classify(
            app_name="NoConfApp", package_name="com.noconf",
            ai_category="", gp_category="",
        )
        assert result is None

    def test_llm_call_passes_response_schema(self, tmp_path: Path) -> None:
        """response_schema should be forwarded to the LLM provider for hard JSON enforcement."""
        client = _mk_client(payload={"category": "银行金融", "confidence": 0.9})
        clf = AppCategoryLLMClassifier(client, _PROMPT_PATH, tmp_path / "c.json")
        clf.classify(
            app_name="NeoBank", package_name="com.neobank",
            ai_category="finance", gp_category="finance",
        )
        kwargs = client.generate_structured.call_args.kwargs
        schema = kwargs.get("response_schema")
        assert isinstance(schema, dict)
        assert schema["type"] == "object"
        assert "category" in schema["properties"]
        assert "confidence" in schema["properties"]
        assert set(schema["properties"]["category"]["enum"]) == set(ALLOWED_CATEGORIES)

    def test_llm_returns_unknown_treated_as_miss(self, tmp_path: Path) -> None:
        """LLM 自己不确定时返回 '其他待归类' → 当 miss 处理，不写正向缓存，保留下次重试机会。"""
        cache_file = tmp_path / "c.json"
        client = _mk_client(payload={"category": "其他待归类"})
        clf = AppCategoryLLMClassifier(client, _PROMPT_PATH, cache_file)
        result = clf.classify(
            app_name="ObscureApp", package_name="com.obscure.x",
            ai_category="", gp_category="",
        )
        assert result is None
        # 不应在缓存中留下正向 category 命中记录
        if cache_file.exists():
            on_disk = json.loads(cache_file.read_text(encoding="utf-8"))
            entry = on_disk.get("obscureapp|com.obscure.x", {})
            assert entry.get("category", "") == ""

    def test_llm_invalid_category_returns_none(self, tmp_path: Path) -> None:
        client = _mk_client(payload={"category": "未知类型"})
        clf = AppCategoryLLMClassifier(client, _PROMPT_PATH, tmp_path / "c.json")
        result = clf.classify(
            app_name="X", package_name="com.x", ai_category="", gp_category="",
        )
        assert result is None

    def test_llm_failure_returns_none(self, tmp_path: Path) -> None:
        client = _mk_client(status="model_unavailable", payload={})
        clf = AppCategoryLLMClassifier(client, _PROMPT_PATH, tmp_path / "c.json")
        result = clf.classify(
            app_name="X", package_name="com.x", ai_category="", gp_category="",
        )
        assert result is None

    def test_empty_app_name_and_package_returns_none(self, tmp_path: Path) -> None:
        client = _mk_client(payload={"category": "银行金融"})
        clf = AppCategoryLLMClassifier(client, _PROMPT_PATH, tmp_path / "c.json")
        result = clf.classify(
            app_name="", package_name="", ai_category="", gp_category="",
        )
        assert result is None
        client.generate_structured.assert_not_called()

    def test_allowed_categories_set_includes_unknown(self) -> None:
        assert "其他待归类" in ALLOWED_CATEGORIES
        assert len(ALLOWED_CATEGORIES) == 10
