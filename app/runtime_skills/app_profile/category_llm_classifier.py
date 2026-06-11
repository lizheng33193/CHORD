"""LLM-backed fallback classifier for app localized_category.

仅当 9 个关键词规则全部 miss 时才会被调用。失败 / mock 模式 / 非法标签
统一返回 None，让调用方走原 UNKNOWN_CATEGORY_LABEL 兜底，保证向后兼容。

设计原理（参考 LLM 工具调用笔记 + comprehensive-refactor-plan）：
1. structured output 模式：传 ``response_schema`` 到 ModelClient，由 Gemini 服务端
   强制 JSON Schema 校验，避免 markdown 代码块 / 缺字段。
2. ``fallback_reason`` 显式枚举：写进 cache + log，事后可归因。
3. ``classify`` 仍只对外返回 ``str | None``；调用方关心结果不关心原因。
"""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.core.logger import get_logger
from app.core.model_client import ModelClient


logger = get_logger(__name__)

ALLOWED_CATEGORIES: frozenset[str] = frozenset(
    {
        "汇款",
        "借贷竞争",
        "政府公共服务",
        "银行金融",
        "社交媒体",
        "出行外卖",
        "电商消费",
        "教育职业",
        "游戏娱乐",
        "其他待归类",
    }
)

# 低于该阈值的 LLM 输出被当 miss 处理（参考 Agent 实战笔记 Q3.3 中、低置信度处理）。
_MIN_CONFIDENCE: float = 0.6

# JSON Schema：传给 ModelClient.generate_structured 的 response_schema 参数，
# 由 Gemini 服务端硬约束输出。enum 直接限定 category 取值。
_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": sorted(ALLOWED_CATEGORIES)},
        "confidence": {"type": "number"},
        "reasoning": {"type": "string"},
    },
    "required": ["category", "confidence"],
}


class AppCategoryLLMClassifier:
    """Per-app LLM classifier with persistent file cache.

    缓存 key: f"{app_name.lower()}|{package_name.lower()}"
    无命中、调用失败、模式为 mock、返回非法标签 → 返回 None。
    """

    def __init__(
        self,
        model_client: ModelClient,
        prompt_path: Path,
        cache_path: Path,
    ) -> None:
        self.model_client = model_client
        self.prompt_path = prompt_path
        self.cache_path = cache_path
        self._template_cache: str | None = None
        self._cache: dict[str, dict[str, Any]] = self._load_cache()
        self._lock = threading.Lock()
        self._defer_persist: bool = False

    def classify(
        self,
        *,
        app_name: str,
        package_name: str,
        ai_category: str,
        gp_category: str,
    ) -> str | None:
        key = self._make_key(app_name, package_name)
        if not key:
            return None

        cached = self._cache.get(key)
        if isinstance(cached, dict):
            cached_cat = cached.get("category")
            if cached_cat in ALLOWED_CATEGORIES:
                return str(cached_cat)
            # Negative cache: previously a miss/low-confidence/illegal — honor it
            # to avoid re-firing the LLM on every analyze.
            if "fallback_reason" in cached:
                return None

        if self.model_client.mode == "mock":
            return None

        prompt = self._build_prompt(app_name, package_name, ai_category, gp_category)
        response = self.model_client.generate_structured(
            skill_name="app_category_classifier",
            prompt=prompt,
            fallback_result={"category": "其他待归类"},
            response_schema=_RESPONSE_SCHEMA,
        )
        if not isinstance(response, dict) or response.get("status") != "ok":
            self._record_miss(
                key, app_name,
                fallback_reason=str(response.get("status", "unknown") if isinstance(response, dict) else "unknown"),
                model_error=str(response.get("structured_result", {}).get("model_error", ""))
                    if isinstance(response, dict) else "",
            )
            return None

        payload = response.get("structured_result") or {}
        if not isinstance(payload, dict):
            self._record_miss(key, app_name, fallback_reason="payload_not_dict")
            return None
        category = str(payload.get("category", "") or "").strip()
        if category not in ALLOWED_CATEGORIES:
            logger.warning(
                "app_category_classifier rejected illegal label app=%s label=%s",
                app_name,
                category,
            )
            self._record_miss(key, app_name, fallback_reason=f"illegal_label:{category!r}")
            return None
        if category == "其他待归类":
            # LLM 自己也拿不准 → 当 miss 处理（避免覆盖原 UNKNOWN，保留下次重试机会）
            return None

        # 置信度过滤：参考 Agent 实战笔记 Q3.3，低置信度不采纳、不写正向缓存。
        try:
            confidence = float(payload.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < _MIN_CONFIDENCE:
            logger.info(
                "app_category_classifier low_confidence app=%s label=%s conf=%.2f",
                app_name,
                category,
                confidence,
            )
            self._record_miss(
                key, app_name,
                fallback_reason=f"low_confidence:{confidence:.2f}:{category}",
            )
            return None

        self._cache[key] = {
            "category": category,
            "confidence": round(confidence, 3),
            "reasoning": str(payload.get("reasoning", "") or "")[:80],
            "model_name": str(response.get("model_name", "")),
            "ts": datetime.now(timezone.utc).isoformat(),
            "fallback_reason": "",
        }
        self._persist_cache()
        logger.info(
            "app_category_classifier hit app=%s -> %s (conf=%.2f)",
            app_name,
            category,
            confidence,
        )
        return category

    # --- internals ---

    @staticmethod
    def _make_key(app_name: str, package_name: str) -> str:
        a = (app_name or "").strip().lower()
        p = (package_name or "").strip().lower()
        if not a and not p:
            return ""
        return f"{a}|{p}"

    def _record_miss(
        self,
        key: str,
        app_name: str,
        *,
        fallback_reason: str,
        model_error: str = "",
    ) -> None:
        """Persist miss reason for offline analysis. Cached entry has no `category`,
        so cache lookup will not return it as a positive hit."""
        self._cache[key] = {
            "category": "",
            "fallback_reason": fallback_reason,
            "model_error": model_error,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self._persist_cache()
        logger.info(
            "app_category_classifier miss app=%s reason=%s",
            app_name,
            fallback_reason,
        )

    def _load_cache(self) -> dict[str, dict[str, Any]]:
        if not self.cache_path.exists():
            return {}
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception as exc:  # noqa: BLE001
            logger.warning("app_category_cache load failed: %s", exc)
        return {}

    def _persist_cache(self) -> None:
        if self._defer_persist:
            return
        with self._lock:
            try:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                self.cache_path.write_text(
                    json.dumps(self._cache, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("app_category_cache persist failed: %s", exc)

    def prefetch_many(
        self,
        items: Iterable[dict[str, str]],
        *,
        max_workers: int = 8,
    ) -> None:
        """Run classify() concurrently for many apps. Each item must have keys
        app_name / package_name / ai_category / gp_category. Cached entries are
        skipped automatically. File persistence is deferred until the end so
        we only write the JSON once."""
        pending: list[dict[str, str]] = []
        for it in items:
            key = self._make_key(it.get("app_name", ""), it.get("package_name", ""))
            if not key or key in self._cache:
                continue
            pending.append(it)
        if not pending:
            return
        logger.info(
            "app_category_classifier prefetch start n=%d workers=%d",
            len(pending),
            max_workers,
        )
        self._defer_persist = True
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = [
                    pool.submit(
                        self.classify,
                        app_name=it.get("app_name", ""),
                        package_name=it.get("package_name", ""),
                        ai_category=it.get("ai_category", ""),
                        gp_category=it.get("gp_category", ""),
                    )
                    for it in pending
                ]
                done = 0
                for _ in as_completed(futures):
                    done += 1
                    if done % 10 == 0 or done == len(futures):
                        logger.info(
                            "app_category_classifier prefetch progress %d/%d",
                            done,
                            len(futures),
                        )
        finally:
            self._defer_persist = False
            self._persist_cache()

    def _load_template(self) -> str:
        if self._template_cache is None:
            self._template_cache = self.prompt_path.read_text(encoding="utf-8")
        return self._template_cache

    def _build_prompt(
        self,
        app_name: str,
        package_name: str,
        ai_category: str,
        gp_category: str,
    ) -> str:
        template = self._load_template()
        payload = {
            "app_name": app_name,
            "package_name": package_name,
            "raw_ai_category": ai_category,
            "raw_gp_category": gp_category,
        }
        return (
            f"{template}\n\n## Input\n```json\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n```\n"
        )
