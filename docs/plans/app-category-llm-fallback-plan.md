# App 分类 LLM 兜底 — 执行 Plan

**日期**：2026-04-28
**关联背景**：现有 `_infer_localized_category` 用 9 个硬编码关键词列表匹配 app，新 app 一律落到 `"其他待归类"`，导致下游 `is_lending_app / is_bank_app / is_consumption_app` 等 6 个 boolean 信号漏判，**进而影响多头借贷风险、金融成熟度、消费能力评估**等核心业务判断。
**总 Task 数**：5（Task 0 baseline + Task 1-4 实现）
**push 策略**：仅本地 commit，不 push。

---

## Scope

### In scope
- 在 `app/scripts/app_profile_payload_builder.py` 的 `_infer_localized_category` **末尾增加 LLM 兜底**：规则全部 miss 时（即将返回 `UNKNOWN_CATEGORY_LABEL` 之前）调 LLM。
- 新增 `app/runtime_skills/app_profile/category_llm_classifier.py`：封装 LLM 调用 + 文件缓存（`outputs/cache/app_category_cache.json`）。
- 新增 `app/prompts/app_category_classifier_prompt.md`。
- 改造 `_with_time_features` / `build_app_feature_bundle` 让 classifier 可注入（依赖注入），默认 `None` = 走原行为，保持向后兼容。
- 在 `app/runtime_skills/app_profile/data_access.py` 处把 classifier 注入到 builder（统一从 ModelClient 实例化）。
- 新增 `tests/test_app_category_llm_classifier.py`（≥ 6 个 case：cache 命中/未命中、LLM 成功/失败、9 类标签 schema 校验、mock 模式 skip）。

### Out of scope
- 不动 9 个 `*_KEYWORDS` 列表（保留作为 fast-path）。
- 不动 `category_label`（一级分类）的逻辑。
- 不动 explainer / decision_engine / assembler。
- 不重写 `app_profile_payload_builder.py` 的整体结构（只在一个函数末尾增加分支 + 注入参数）。
- 不做批量调用（每 app 单独调，但用文件 cache 让相同 app 全局只调一次）。

### 设计要点
- **9 个本地化分类标签固定**：`{"汇款", "借贷竞争", "政府公共服务", "银行金融", "社交媒体", "出行外卖", "电商消费", "教育职业", "游戏娱乐", "其他待归类"}`。LLM 必须从这 10 个里选一个，schema 强约束。
- **缓存 key**：`{app_name_lower}|{package_name_lower}` —— 同一 app 在所有用户分析里只调 1 次 LLM。
- **缓存文件**：`outputs/cache/app_category_cache.json`，结构 `{key: {"category": "...", "model_name": "...", "ts": "..."}}`。每次调用 LLM 后立即写盘（容错丢失）。
- **mock 模式行为**：classifier 直接返回 `None`，让原 `UNKNOWN_CATEGORY_LABEL` 回退继续工作 → 测试零新增 LLM 依赖。
- **LLM 失败容忍**：超时/解析失败/返回非合法标签 → classifier 返回 `None`，原 `UNKNOWN_CATEGORY_LABEL` 兜底（不破坏现有行为）。

---

## Task 0 — Baseline + git status check

```bash
git status                                  # 应 clean（前一个 overlay commit 已落）
git rev-parse HEAD                          # 记录基线 SHA
python -m pytest tests/ -q --tb=short       # 应 94 passed
git commit --allow-empty -m "[baseline] app-category-llm-fallback"
```

预期：clean / 94 passed / baseline commit 落盘。

---

## Task 1 — 新建 classifier + prompt + 缓存层（含单测）

### 文件操作
- **Create** `app/prompts/app_category_classifier_prompt.md`
- **Create** `app/runtime_skills/app_profile/category_llm_classifier.py`
- **Create** `tests/test_app_category_llm_classifier.py`
- **Modify** `.gitignore`（追加 `outputs/cache/app_category_cache.json` 不入库）

### 1.1 `app/prompts/app_category_classifier_prompt.md`

内容大纲（不超过 30 行）：

```
你是墨西哥金融 App 风控分类助手。给定一个 App 的 name + package + raw_category，
从下列 9 个固定标签里选一个返回 JSON：

允许标签：["汇款", "借贷竞争", "政府公共服务", "银行金融", "社交媒体", "出行外卖",
         "电商消费", "教育职业", "游戏娱乐", "其他待归类"]

判断要点：
- "借贷竞争"：现金贷 / 短期借贷 app（kueski / baubap / tala / cashly 等）
- "银行金融"：传统银行、电子钱包、券商、保险（BBVA / Nu / Mercado Pago / Spin）
- "政府公共服务"：政府 / 税务 / 社保 / 公共事业 (SAT / IMSS / CFE)
- "汇款"：跨境汇款 (Remitly / Wise / Western Union)
- "出行外卖"：打车 / 外卖 / 旅行 (Uber / DiDi / Rappi / Booking)
- "电商消费"：电商 / 零售 / BNPL (Mercado Libre / Amazon / Shein / Aplazo)
- "社交媒体"：通讯 / 社交 (WhatsApp / Facebook / TikTok)
- "游戏娱乐"：手游 / 视频 / 音乐
- "教育职业"：求职 / 在线教育 (Coursera / Indeed)
- "其他待归类"：以上都不沾边

只输出 JSON：{"category": "<标签>", "reasoning": "<不超过 40 字>"}
```

### 1.2 `app/runtime_skills/app_profile/category_llm_classifier.py`

```python
"""LLM-backed fallback classifier for app localized_category.

调用入口：仅当 9 个关键词规则全部 miss 时被调用。失败/mock 模式返回 None，
让原 UNKNOWN_CATEGORY_LABEL 继续兜底，保证向后兼容。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.logger import get_logger
from app.core.model_client import ModelClient


logger = get_logger(__name__)

ALLOWED_CATEGORIES: frozenset[str] = frozenset({
    "汇款", "借贷竞争", "政府公共服务", "银行金融", "社交媒体",
    "出行外卖", "电商消费", "教育职业", "游戏娱乐", "其他待归类",
})


class AppCategoryLLMClassifier:
    """Per-app LLM classifier with persistent file cache.

    缓存 key: f"{app_name.lower()}|{package_name.lower()}"
    无命中、调用失败、模式为 mock → 返回 None（让调用方走原回退路径）。
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
        if cached and cached.get("category") in ALLOWED_CATEGORIES:
            return str(cached["category"])

        if self.model_client.mode == "mock":
            return None

        prompt = self._build_prompt(app_name, package_name, ai_category, gp_category)
        response = self.model_client.generate_structured(
            skill_name="app_category_classifier",
            prompt=prompt,
            fallback_result={"category": "其他待归类"},
        )
        if response.get("status") != "ok":
            return None

        payload = response.get("structured_result") or {}
        if not isinstance(payload, dict):
            return None
        category = str(payload.get("category", "") or "").strip()
        if category not in ALLOWED_CATEGORIES:
            return None

        self._cache[key] = {
            "category": category,
            "model_name": str(response.get("model_name", "")),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self._persist_cache()
        return category

    # --- internals ---
    @staticmethod
    def _make_key(app_name: str, package_name: str) -> str:
        a = (app_name or "").strip().lower()
        p = (package_name or "").strip().lower()
        if not a and not p:
            return ""
        return f"{a}|{p}"

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
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("app_category_cache persist failed: %s", exc)

    def _load_template(self) -> str:
        if self._template_cache is None:
            self._template_cache = self.prompt_path.read_text(encoding="utf-8")
        return self._template_cache

    def _build_prompt(
        self, app_name: str, package_name: str, ai_category: str, gp_category: str,
    ) -> str:
        template = self._load_template()
        payload = {
            "app_name": app_name,
            "package_name": package_name,
            "raw_ai_category": ai_category,
            "raw_gp_category": gp_category,
        }
        return f"{template}\n\n## Input\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```\n"
```

### 1.3 `tests/test_app_category_llm_classifier.py`

5 个 case：
- `test_mock_mode_returns_none`：`mode="mock"` → `classify()` 返回 `None`，未调用 `generate_structured`。
- `test_cache_hit_skips_llm`：预置 `_cache[key]` = "银行金融"；返回该值；不调 LLM。
- `test_llm_ok_writes_cache`：mock client 返回 `{"category":"借贷竞争"}`；返回该值；cache 文件含 key。
- `test_llm_invalid_category_returns_none`：mock 返回 `{"category":"未知类型"}`（不在 ALLOWED）→ 返回 `None`。
- `test_llm_failure_returns_none`：mock client `status="model_unavailable"` → 返回 `None`。
- `test_empty_app_name_and_package_returns_none`：两者都空 → `None`，不调 LLM。

每个测试用 tmp_path 隔离 cache 文件；用 `MagicMock(spec=ModelClient)` 控制 `mode` 与 `generate_structured.return_value`。

### 1.4 验证
```bash
python -m pytest tests/test_app_category_llm_classifier.py -v
```
预期 6 passed。

### 1.5 Commit
```bash
git add app/prompts/app_category_classifier_prompt.md \
        app/runtime_skills/app_profile/category_llm_classifier.py \
        tests/test_app_category_llm_classifier.py .gitignore
git commit -m "feat(app-profile): add LLM category classifier with file cache"
```

---

## Task 2 — 在 `_infer_localized_category` 末尾接入 classifier

### 文件操作
- **Modify** `app/scripts/app_profile_payload_builder.py`（仅 `_infer_localized_category` 与 `_with_time_features` 与 `build_app_feature_bundle`）

### 2.1 修改点

1. `_infer_localized_category` 增加可选参数 `classifier: AppCategoryLLMClassifier | None = None`；在两段规则都 miss、即将返回 `UNKNOWN_CATEGORY_LABEL` 之前，改为：
   ```python
   if classifier is not None:
       inferred = classifier.classify(
           app_name=app_name, package_name=package_name,
           ai_category=ai_category, gp_category=gp_category,
       )
       if inferred:
           return inferred
   return UNKNOWN_CATEGORY_LABEL
   ```
2. `_with_time_features` 增加同名参数并透传。
3. `build_app_feature_bundle` 增加 `classifier=None` 参数并透传到 `_with_time_features`。

向后兼容：所有现有 caller 不传该参数 → `None` → 行为完全等同今天。

### 2.2 验证
```bash
python -m pytest tests/ -q --tb=short
```
预期：94 + 6（Task 1 新增）= 100 passed。

### 2.3 Commit
```bash
git add app/scripts/app_profile_payload_builder.py
git commit -m "feat(app-profile): wire optional LLM classifier into category inference"
```

---

## Task 3 — 在运行时 data_access 层注入 classifier

### 文件操作
- **Modify** `app/runtime_skills/app_profile/feature_builder.py`：构造时接受 `model_client`，把 classifier 透传给 `build_app_feature_bundle`。
- **Modify** `app/runtime_skills/app_profile_agent.py`：把 `model_client` 传给 `AppFeatureBuilder`（保持现有签名只是新增依赖）。
- **Modify** `app/core/config.py` 不动；prompt/cache 路径通过 `settings.resolve_path` 拼。

### 3.1 实现

`AppFeatureBuilder.__init__(self, model_client=None)`；如果传入则建 classifier，否则保持 `None`。

```python
class AppFeatureBuilder:
    def __init__(self, model_client: ModelClient | None = None) -> None:
        self._classifier: AppCategoryLLMClassifier | None = None
        if model_client is not None:
            prompt_path = settings.resolve_path(
                f"{settings.prompt_dir}/app_category_classifier_prompt.md"
            )
            cache_path = settings.resolve_path("outputs/cache/app_category_cache.json")
            self._classifier = AppCategoryLLMClassifier(
                model_client=model_client,
                prompt_path=prompt_path,
                cache_path=cache_path,
            )

    def build(self, raw_data, context):
        ...
        return build_app_feature_bundle(
            ..., classifier=self._classifier,
        )
```

`AppProfileSkill.__init__` 把 `model_client` 传给 `AppFeatureBuilder(model_client=model_client)`。

### 3.2 验证

```bash
python -m pytest tests/ -q --tb=short
```
预期：仍 100 passed（mock 模式下 classifier 不调 LLM，行为与今天一致）。

外加一个端到端 smoke：
```bash
$env:MODEL_MODE="mock"; python -c "from app.runtime_skills.app_profile_agent import AppProfileSkill; from app.core.model_client import ModelClient; from app.repositories.local_files import LocalFileUserRepository; s = AppProfileSkill(ModelClient(), LocalFileUserRepository()); print(s.analyze('user_001').get('status'))"
```
预期输出 `ok` 或 `data_missing`，无 traceback。

### 3.3 Commit
```bash
git add app/runtime_skills/app_profile/feature_builder.py \
        app/runtime_skills/app_profile_agent.py
git commit -m "feat(app-profile): inject LLM category classifier into feature builder"
```

---

## Task 4 — 收尾：smoke + 文档

### 4.1 启动 server vertex 模式回归（可选，但推荐）
```bash
# 假设你已经停掉旧 server；重启成 vertex 模式
$env:MODEL_MODE="vertex"; python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
浏览器跑一个 UID，看 evidence 里 `localized_category_distribution` 的"其他待归类"应明显减少。
看 `outputs/cache/app_category_cache.json` 是否生成且有内容。

### 4.2 更新 TASK.md
追加一条已完成：
```
- [x] App 分类 LLM 兜底（2026-04-28，docs/plans/app-category-llm-fallback-plan.md）
```

### 4.3 全量回归 + complete
```bash
python -m pytest tests/ -q --tb=short      # ≥ 100 passed
git add TASK.md
git commit -m "docs(task): mark app-category-llm-fallback complete"
git commit --allow-empty -m "[complete] app-category-llm-fallback"
git log --oneline -8
```

---

## 完工验收清单

- [ ] `_infer_localized_category` 仍兼容无 classifier 调用（向后兼容）
- [ ] mock 模式下 classifier 不调 LLM，行为零变化
- [ ] vertex 模式下未知 app 至少调一次 LLM 并写 cache
- [ ] 同一 app 第二次出现直接命中 cache（log 可观测）
- [ ] 全量 pytest ≥ 100 passed
- [ ] 9 个固定标签外的 LLM 输出被拒绝，回落 `其他待归类`
- [ ] cache 文件不入 git（`.gitignore` 已忽略）
