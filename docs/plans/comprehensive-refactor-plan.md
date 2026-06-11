# Comprehensive Profile 六步管线重构 — 执行 Plan

**关联设计文档**：`docs/specs/comprehensive-refactor-design.md`
**关联 TASK.md 条目**：P1 拆分 Comprehensive 为六步管线
**日期**：2026-04-28
**总 Task 数**：8（Task 0 baseline + Task 1-7 实现）

---

## ⚠️ 执行修正清单（审核后补充，优先级高于下方代码块）

执行每个 Task 时，**必须先读对应的源代码文件**再写实现，不要照抄下方代码块。以下 5 条修正覆盖了 Plan 初版中与实际代码不一致的地方：

| # | Task | 问题 | 修正 |
|---|------|------|------|
| 1 | Task 1 | ~~`settings.enable_llm_explanation` / `settings.default_language` / `settings.default_channel` 不存在~~ | **已修正**：改用 `load_app_country_pack` 模式，与 `build_app_run_context` 对齐 |
| 2 | Task 3 | ~~`_build_*_score` 用了错误字段名（installed_app_count/risky_app_count）~~ | **已修正**：替换为实际字段（active_days_30d / consumption_ability_level / engagement_score 等） |
| 3 | Task 4 | `_assign_segment` 等规则函数的骨架逻辑和实际代码差异大 | **执行时必须**：先全量读 `comprehensive_agent.py` 的对应函数，原样搬运到新文件。下方代码是骨架参考，实际以源码为准 |
| 4 | Task 5 | `ModelClient.generate_structured()` 返回 **dict** 不是对象；签名需要 `skill_name` / `prompt` / `fallback_result` 三个参数 | **执行时必须**：先读 `app/core/model_client.py` 前 100 行确认接口。用 `response["status"]` 不是 `response.status`，用 `response.get("structured_result", {})` 不是 `response.payload` |
| 5 | Task 6 | Pydantic 校验应用 `model_validate_compat` 而非直接 `.model_validate()` | **执行时必须**：用 `from app.utils.pydantic_compat import model_validate_compat, model_dump_compat`；chart 构建用 `build_comprehensive_charts`（from app.scripts.chart_builder），report 用 `render_agent_report`（from app.services.report_renderer） |

---

## Scope（来自设计文档第 2 章）

### In scope
- 在 `app/runtime_skills/comprehensive/` 下新建六步管线文件（contracts / data_access / feature_builder / decision_engine / explainer / assembler）
- 重写 `app/runtime_skills/comprehensive_agent.py` 为薄入口（≤ 80 行），仅编排六步
- 新增 `tests/test_comprehensive_phase1.py`，按 6 个 class 组织单测
- 不破坏 68 测试基线

### Out of scope
- `ComprehensiveProfileStructuredResult` schema 字段重写（另一条 P1）
- behavior/credit 的对齐拆分（已经拆过，本次不动）
- prompt 模板大改（仅追加"哪个上游缺失"的提示句，且条件渲染）
- model_trace 在 behavior/credit 顶层的修复（属于 P0-2 验证发现的另一个独立任务）

---

## 依赖参考代码

| 用途 | 路径 |
|---|---|
| 六步管线参考实现（结构对齐目标） | [app/runtime_skills/app_profile/](../../app/runtime_skills/app_profile/) |
| TypedDict 契约参考 | [app/runtime_skills/app_profile/contracts.py](../../app/runtime_skills/app_profile/contracts.py) |
| data_access 参考 | [app/runtime_skills/app_profile/data_access.py](../../app/runtime_skills/app_profile/data_access.py) |
| feature_builder 参考 | [app/runtime_skills/app_profile/feature_builder.py](../../app/runtime_skills/app_profile/feature_builder.py) |
| decision_engine 参考 | [app/runtime_skills/app_profile/decision_engine.py](../../app/runtime_skills/app_profile/decision_engine.py) |
| explainer / LLM 调用参考 | [app/runtime_skills/app_profile/explainer.py](../../app/runtime_skills/app_profile/explainer.py) |
| assembler 参考 | [app/runtime_skills/app_profile/assembler.py](../../app/runtime_skills/app_profile/assembler.py) |
| 薄入口 Skill 参考 | [app/runtime_skills/app_profile_agent.py](../../app/runtime_skills/app_profile_agent.py) |
| 待重构源文件（512 行，搬代码来源） | [app/runtime_skills/comprehensive_agent.py](../../app/runtime_skills/comprehensive_agent.py) |
| BaseSkill 基类 | [app/runtime_skills/base.py](../../app/runtime_skills/base.py) |
| Skill 注册位置 | [app/services/orchestrator.py](../../app/services/orchestrator.py) |
| ModelClient（LLM 唯一入口） | [app/core/model_client.py](../../app/core/model_client.py) |
| Prompt 模板（待追加一行） | [app/prompts/comprehensive_prompt.md](../../app/prompts/comprehensive_prompt.md) |
| 测试结构参考 | [tests/test_app_profile_phase1.py](../../tests/test_app_profile_phase1.py) |
| Pydantic schema（不改，仅消费） | [app/schemas/comprehensive_profile.py](../../app/schemas/comprehensive_profile.py) |

---

## Task 0 — Baseline commit

**目的**：在动任何代码前固定基线，便于回滚。

**步骤**：
1. 确认 working tree clean：
   ```bash
   git status
   ```
2. 打 baseline commit：
   ```bash
   git commit --allow-empty -m "[baseline] comprehensive-refactor"
   ```
3. 跑全量测试，记录基线数字：
   ```bash
   python -m pytest tests/ -v
   ```

**预期输出**：
- `git status` 报 `nothing to commit, working tree clean`
- baseline commit 创建成功（HEAD 前进一格）
- pytest 报 `68 passed`

**完成标志**：基线 commit 已落盘，68 测试全过。

---

## Task 1 — 建目录骨架 + contracts.py

**目的**：建 `app/runtime_skills/comprehensive/` 目录、写完整 6 个 TypedDict 与 `build_comprehensive_run_context`，`__init__.py` 仅导出 contracts 内容。

### 文件操作
- **Create** `app/runtime_skills/comprehensive/__init__.py`
- **Create** `app/runtime_skills/comprehensive/contracts.py`

### TDD 子步骤

**1.1** 先写一个最小冒烟测试（验证 import 与 `build_comprehensive_run_context` 形状）。

**Create** `tests/test_comprehensive_phase1.py`：

```python
"""Phase-1 unit tests for the six-step comprehensive pipeline."""
from __future__ import annotations

import pytest

from app.runtime_skills.comprehensive import (
    ComprehensiveDecisionResult,
    ComprehensiveExplanationResult,
    ComprehensiveFeatureBundle,
    ComprehensivePageResult,
    ComprehensiveRunContext,
    ComprehensiveUpstreamBundle,
    build_comprehensive_run_context,
)


class TestComprehensiveContracts:
    def test_build_run_context_returns_required_keys(self) -> None:
        ctx = build_comprehensive_run_context("uid-1", application_time=None)
        assert ctx["uid"] == "uid-1"
        assert ctx["country_code"]
        assert ctx["application_time"]
        assert ctx["trace_id"]
        assert isinstance(ctx["enable_llm_explanation"], bool)
        assert ctx["language"]
        assert ctx["channel"]

    def test_typeddicts_are_importable(self) -> None:
        # 仅验证导出存在，TypedDict 在 runtime 是 dict
        for cls in (
            ComprehensiveRunContext,
            ComprehensiveUpstreamBundle,
            ComprehensiveFeatureBundle,
            ComprehensiveDecisionResult,
            ComprehensiveExplanationResult,
            ComprehensivePageResult,
        ):
            assert cls is not None
```

**1.2** 跑测试，确认失败（ImportError，因为 `comprehensive` 包尚未存在）：

```bash
python -m pytest tests/test_comprehensive_phase1.py::TestComprehensiveContracts -v
```

预期：`ImportError: No module named 'app.runtime_skills.comprehensive'`。

**1.3** 写实现。

**Create** `app/runtime_skills/comprehensive/contracts.py`：

```python
"""Type contracts for the comprehensive six-step pipeline.

fallback_reason 已知取值（自由字符串，不强枚举）：
    ""                                       LLM 被采纳
    "upstream_all_missing"                   data_missing 路径
    "model_mode_mock"
    "empty_explanation_payload"
    "schema_validation_failed: <exc>"
    "<model_client status>"                  例如 timeout / json_parse_error / http_<code>
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypedDict

from app.core.config import settings
from app.country_packs.app_profile import load_app_country_pack


class ComprehensiveRunContext(TypedDict):
    uid: str
    country_code: str
    application_time: str
    trace_id: str
    enable_llm_explanation: bool
    language: str
    channel: str


class ComprehensiveUpstreamBundle(TypedDict):
    uid: str
    country_code: str
    app_result: dict[str, Any]
    behavior_result: dict[str, Any]
    credit_result: dict[str, Any]
    app_status: str
    behavior_status: str
    credit_status: str
    ok_count: int
    missing_modules: list[str]
    data_status: str
    errors: list[str]


class ComprehensiveFeatureBundle(TypedDict):
    uid: str
    country_code: str
    app_metrics: dict[str, Any]
    behavior_metrics: dict[str, Any]
    credit_metrics: dict[str, Any]
    app_score: int
    behavior_score: int
    credit_score: int
    upstream_summaries: dict[str, str]
    feature_status: str
    errors: list[str]


class ComprehensiveDecisionResult(TypedDict):
    uid: str
    country_code: str
    decision_status: str
    segment: str
    overall_risk_level: str
    value_signal_level: str
    confidence_level: str
    conflict_explanations: list[str]
    persona_seed: str
    tags_rule: list[str]
    metrics: dict[str, Any]
    errors: list[str]


class ComprehensiveExplanationResult(TypedDict):
    uid: str
    country_code: str
    explanation_status: str
    used_llm: bool
    summary: str
    persona: str
    tags_addon: list[str]
    conflict_explanations: list[str]
    reasoning_texts: dict[str, str]
    model_trace: dict[str, Any]
    errors: list[str]


class ComprehensivePageResult(TypedDict):
    summary: str
    structured_result: dict[str, Any]
    charts: list[dict[str, Any]]
    report_markdown: str


def build_comprehensive_run_context(
    uid: str,
    *,
    application_time: str | None = None,
    country_code: str | None = None,
    trace_id: str = "",
    enable_llm_explanation: bool = True,
    language: str | None = None,
    channel: str = "api",
) -> ComprehensiveRunContext:
    """Create a stable run context for the comprehensive pipeline.

    Mirrors build_app_run_context in app/runtime_skills/app_profile/contracts.py.
    """
    pack = load_app_country_pack(country_code or settings.default_country_code)
    application_time_value = application_time or datetime.now(timezone.utc).isoformat()
    return {
        "uid": uid,
        "country_code": pack.country_code,
        "application_time": application_time_value,
        "trace_id": trace_id,
        "enable_llm_explanation": enable_llm_explanation,
        "language": language or pack.default_language,
        "channel": channel or "api",
    }
```

**Create** `app/runtime_skills/comprehensive/__init__.py`：

```python
"""Comprehensive profile pipeline (six-step structure)."""
from app.runtime_skills.comprehensive.contracts import (
    ComprehensiveDecisionResult,
    ComprehensiveExplanationResult,
    ComprehensiveFeatureBundle,
    ComprehensivePageResult,
    ComprehensiveRunContext,
    ComprehensiveUpstreamBundle,
    build_comprehensive_run_context,
)

__all__ = [
    "ComprehensiveDecisionResult",
    "ComprehensiveExplanationResult",
    "ComprehensiveFeatureBundle",
    "ComprehensivePageResult",
    "ComprehensiveRunContext",
    "ComprehensiveUpstreamBundle",
    "build_comprehensive_run_context",
]
```

**1.4** 验证：

```bash
python -c "from app.runtime_skills.comprehensive import build_comprehensive_run_context; print(build_comprehensive_run_context('test-uid'))"
python -m pytest tests/test_comprehensive_phase1.py::TestComprehensiveContracts -v
```

预期：
- `python -c` 输出包含 `'uid': 'test-uid'` 的 dict
- pytest 报 `2 passed`

**1.5** 注：若 `settings` 中无 `default_language` / `default_channel` / `enable_llm_explanation` / `default_country_code` 字段，参考 `build_app_run_context` 在 `app/runtime_skills/app_profile/contracts.py` 的对应实现保持一致；如名称不同，按已存在字段调整。

**1.6** Commit：
```bash
git add app/runtime_skills/comprehensive/ tests/test_comprehensive_phase1.py
git commit -m "feat(comprehensive): add contracts + run-context skeleton"
```

---

## Task 2 — data_access.py：ComprehensiveUpstreamProvider

**目的**：把上游三个 Skill result 的健康解包封到一个薄壳里。

### 文件操作
- **Create** `app/runtime_skills/comprehensive/data_access.py`
- **Modify** `app/runtime_skills/comprehensive/__init__.py`（追加 `ComprehensiveUpstreamProvider` 导出）
- **Modify** `tests/test_comprehensive_phase1.py`（追加 `TestComprehensiveUpstreamProvider`）

### TDD 子步骤

**2.1** 先在 `tests/test_comprehensive_phase1.py` 末尾追加测试 class：

```python
from app.runtime_skills.comprehensive import ComprehensiveUpstreamProvider


def _ok_skill_result(name: str) -> dict:
    return {
        "status": "ok",
        "structured_result": {"summary": f"{name} ok"},
    }


def _missing_skill_result() -> dict:
    return {"status": "data_missing", "structured_result": {}}


class TestComprehensiveUpstreamProvider:
    def setup_method(self) -> None:
        self.provider = ComprehensiveUpstreamProvider()
        self.context = build_comprehensive_run_context("uid-2")

    def test_all_three_ok(self) -> None:
        bundle = self.provider.fetch(
            "uid-2", self.context,
            app_result=_ok_skill_result("app"),
            behavior_result=_ok_skill_result("behavior"),
            credit_result=_ok_skill_result("credit"),
        )
        assert bundle["ok_count"] == 3
        assert bundle["missing_modules"] == []
        assert bundle["data_status"] == "ok"

    def test_partial_missing(self) -> None:
        bundle = self.provider.fetch(
            "uid-2", self.context,
            app_result=_ok_skill_result("app"),
            behavior_result=_missing_skill_result(),
            credit_result=_ok_skill_result("credit"),
        )
        assert bundle["ok_count"] == 2
        assert "behavior_profile" in bundle["missing_modules"]
        assert bundle["data_status"] == "ok"

    def test_all_missing_triggers_data_missing(self) -> None:
        bundle = self.provider.fetch(
            "uid-2", self.context,
            app_result=_missing_skill_result(),
            behavior_result=_missing_skill_result(),
            credit_result=_missing_skill_result(),
        )
        assert bundle["ok_count"] == 0
        assert bundle["data_status"] == "data_missing"
        assert set(bundle["missing_modules"]) == {
            "app_profile", "behavior_profile", "credit_profile",
        }

    def test_non_dict_structured_is_tolerated(self) -> None:
        bad = {"status": "ok", "structured_result": "not-a-dict"}
        bundle = self.provider.fetch(
            "uid-2", self.context,
            app_result=bad,
            behavior_result=_ok_skill_result("behavior"),
            credit_result=_ok_skill_result("credit"),
        )
        assert "app_profile" in bundle["missing_modules"]
        assert bundle["ok_count"] == 2
```

**2.2** 跑测试，确认失败（ImportError on `ComprehensiveUpstreamProvider`）：

```bash
python -m pytest tests/test_comprehensive_phase1.py::TestComprehensiveUpstreamProvider -v
```

**2.3** 写实现。

**Create** `app/runtime_skills/comprehensive/data_access.py`：

```python
"""Upstream skill-result aggregation for the comprehensive pipeline."""
from __future__ import annotations

from typing import Any

from app.runtime_skills.comprehensive.contracts import (
    ComprehensiveRunContext,
    ComprehensiveUpstreamBundle,
)


class ComprehensiveUpstreamProvider:
    """Thin shell that normalises three upstream skill results."""

    _MODULE_KEYS: tuple[tuple[str, str], ...] = (
        ("app_result", "app_profile"),
        ("behavior_result", "behavior_profile"),
        ("credit_result", "credit_profile"),
    )

    def fetch(
        self,
        uid: str,
        context: ComprehensiveRunContext,
        *,
        app_result: dict[str, Any],
        behavior_result: dict[str, Any],
        credit_result: dict[str, Any],
    ) -> ComprehensiveUpstreamBundle:
        results = {
            "app_result": app_result or {},
            "behavior_result": behavior_result or {},
            "credit_result": credit_result or {},
        }
        statuses: dict[str, str] = {}
        missing: list[str] = []
        errors: list[str] = []
        ok_count = 0

        for result_key, module_name in self._MODULE_KEYS:
            res = results[result_key]
            status_raw = res.get("status") if isinstance(res, dict) else None
            structured = res.get("structured_result") if isinstance(res, dict) else None
            if status_raw == "ok" and isinstance(structured, dict) and structured:
                statuses[module_name] = "ok"
                ok_count += 1
            else:
                statuses[module_name] = "missing" if status_raw != "ok" else "degraded"
                missing.append(module_name)
                if status_raw and status_raw != "ok":
                    errors.append(f"{module_name}:{status_raw}")

        data_status = "ok" if ok_count >= 1 else "data_missing"

        return ComprehensiveUpstreamBundle(
            uid=uid,
            country_code=context["country_code"],
            app_result=results["app_result"],
            behavior_result=results["behavior_result"],
            credit_result=results["credit_result"],
            app_status=statuses["app_profile"],
            behavior_status=statuses["behavior_profile"],
            credit_status=statuses["credit_profile"],
            ok_count=ok_count,
            missing_modules=missing,
            data_status=data_status,
            errors=errors,
        )
```

**2.4** 更新 `app/runtime_skills/comprehensive/__init__.py`（追加导出）：

```python
"""Comprehensive profile pipeline (six-step structure)."""
from app.runtime_skills.comprehensive.contracts import (
    ComprehensiveDecisionResult,
    ComprehensiveExplanationResult,
    ComprehensiveFeatureBundle,
    ComprehensivePageResult,
    ComprehensiveRunContext,
    ComprehensiveUpstreamBundle,
    build_comprehensive_run_context,
)
from app.runtime_skills.comprehensive.data_access import (
    ComprehensiveUpstreamProvider,
)

__all__ = [
    "ComprehensiveDecisionResult",
    "ComprehensiveExplanationResult",
    "ComprehensiveFeatureBundle",
    "ComprehensivePageResult",
    "ComprehensiveRunContext",
    "ComprehensiveUpstreamBundle",
    "ComprehensiveUpstreamProvider",
    "build_comprehensive_run_context",
]
```

**2.5** 验证：

```bash
python -m pytest tests/test_comprehensive_phase1.py::TestComprehensiveUpstreamProvider -v
```

预期：`4 passed`。

**2.6** Commit：
```bash
git add app/runtime_skills/comprehensive/ tests/test_comprehensive_phase1.py
git commit -m "feat(comprehensive): add upstream provider"
```

---

## Task 3 — feature_builder.py：ComprehensiveFeatureBuilder

**目的**：把数值抽取（含 score）从 `comprehensive_agent.py` 搬到独立模块；不做任何判断派生。

### 文件操作
- **Create** `app/runtime_skills/comprehensive/feature_builder.py`
- **Modify** `app/runtime_skills/comprehensive/__init__.py`（追加导出）
- **Modify** `tests/test_comprehensive_phase1.py`（追加 `TestComprehensiveFeatureBuilder`）

### TDD 子步骤

**3.1** 在 `tests/test_comprehensive_phase1.py` 末尾追加测试 class：

```python
from app.runtime_skills.comprehensive import ComprehensiveFeatureBuilder


def _bundle_all_ok(uid: str = "uid-3") -> "ComprehensiveUpstreamBundle":
    provider = ComprehensiveUpstreamProvider()
    ctx = build_comprehensive_run_context(uid)
    return provider.fetch(
        uid, ctx,
        app_result={"status": "ok", "structured_result": {
            "summary": "App summary",
            "activity_level": "high",
            "metrics": {"active_days_30d": 24, "consumption_ability_level": "high",
                        "financial_maturity_level": "banked", "multi_loan_risk_level": "low"},
            "tags": [],
        }},
        behavior_result={"status": "ok", "structured_result": {
            "summary": "Behavior summary",
            "engagement_level": "deep",
            "metrics": {"engagement_score": 80, "repayment_willingness_level": "high",
                        "churn_risk_level": "low", "product_sensitivity_level": "medium"},
            "tags": [],
        }},
        credit_result={"status": "ok", "structured_result": {
            "summary": "Credit summary",
            "status": "ok",
            "metrics": {"risk_level": "low", "credit_stability_level": "high",
                        "debt_pressure_level": "low"},
            "tags": [],
        }},
    )


class TestComprehensiveFeatureBuilder:
    def setup_method(self) -> None:
        self.builder = ComprehensiveFeatureBuilder()
        self.context = build_comprehensive_run_context("uid-3")

    def test_all_ok_produces_full_bundle(self) -> None:
        bundle = self.builder.build(_bundle_all_ok(), self.context)
        assert bundle["feature_status"] == "ok"
        assert 1 <= bundle["app_score"] <= 5
        assert 1 <= bundle["behavior_score"] <= 5
        assert 1 <= bundle["credit_score"] <= 5
        assert set(bundle["upstream_summaries"]) == {
            "app_profile", "behavior_profile", "credit_profile",
        }

    def test_missing_upstream_yields_zero_score_and_empty_metrics(self) -> None:
        provider = ComprehensiveUpstreamProvider()
        upstream = provider.fetch(
            "uid-3", self.context,
            app_result={"status": "ok", "structured_result": {"summary": "ok", "metrics": {}}},
            behavior_result={"status": "data_missing", "structured_result": {}},
            credit_result={"status": "ok", "structured_result": {"summary": "ok", "metrics": {}}},
        )
        bundle = self.builder.build(upstream, self.context)
        assert bundle["behavior_metrics"] == {}
        assert bundle["behavior_score"] == 0

    def test_score_is_clamped_to_1_5_range(self) -> None:
        bundle = self.builder.build(_bundle_all_ok(), self.context)
        for s in (bundle["app_score"], bundle["behavior_score"], bundle["credit_score"]):
            assert 0 <= s <= 5
```

**3.2** 跑测试，确认失败：

```bash
python -m pytest tests/test_comprehensive_phase1.py::TestComprehensiveFeatureBuilder -v
```

**3.3** 写实现。**Create** `app/runtime_skills/comprehensive/feature_builder.py`：

```python
"""Numeric feature extraction for the comprehensive pipeline (no judgement)."""
from __future__ import annotations

from typing import Any

from app.runtime_skills.comprehensive.contracts import (
    ComprehensiveFeatureBundle,
    ComprehensiveRunContext,
    ComprehensiveUpstreamBundle,
)


class ComprehensiveFeatureBuilder:
    """Extract metrics + summaries from upstream results, derive 1-5 scores.

    搬自原 comprehensive_agent._build_*_score / _extract_metrics 逻辑。
    缺失上游：metrics 置空 dict，score=0。
    """

    def build(
        self,
        upstream: ComprehensiveUpstreamBundle,
        context: ComprehensiveRunContext,
    ) -> ComprehensiveFeatureBundle:
        errors: list[str] = []

        app_metrics = self._extract_metrics(upstream["app_result"], "app_profile") if upstream["app_status"] == "ok" else {}
        behavior_metrics = self._extract_metrics(upstream["behavior_result"], "behavior_profile") if upstream["behavior_status"] == "ok" else {}
        credit_metrics = self._extract_metrics(upstream["credit_result"], "credit_profile") if upstream["credit_status"] == "ok" else {}

        app_score = self._build_app_score(app_metrics) if app_metrics else 0
        behavior_score = self._build_behavior_score(behavior_metrics) if behavior_metrics else 0
        credit_score = self._build_credit_score(credit_metrics) if credit_metrics else 0

        summaries = self._build_upstream_summaries(upstream)

        return ComprehensiveFeatureBundle(
            uid=upstream["uid"],
            country_code=context["country_code"],
            app_metrics=app_metrics,
            behavior_metrics=behavior_metrics,
            credit_metrics=credit_metrics,
            app_score=app_score,
            behavior_score=behavior_score,
            credit_score=credit_score,
            upstream_summaries=summaries,
            feature_status="ok",
            errors=errors,
        )

    @staticmethod
    def _extract_metrics(skill_result: dict[str, Any], _module: str) -> dict[str, Any]:
        sr = skill_result.get("structured_result") if isinstance(skill_result, dict) else None
        if not isinstance(sr, dict):
            return {}
        metrics = sr.get("metrics")
        return metrics if isinstance(metrics, dict) else {}

    @staticmethod
    def _build_upstream_summaries(upstream: ComprehensiveUpstreamBundle) -> dict[str, str]:
        out: dict[str, str] = {}
        for result_key, module in (
            ("app_result", "app_profile"),
            ("behavior_result", "behavior_profile"),
            ("credit_result", "credit_profile"),
        ):
            res = upstream[result_key]  # type: ignore[literal-required]
            sr = res.get("structured_result") if isinstance(res, dict) else None
            summary = ""
            if isinstance(sr, dict):
                raw = sr.get("summary")
                if isinstance(raw, str):
                    summary = raw
            out[module] = summary
        return out

    @staticmethod
    def _build_app_score(metrics: dict[str, Any]) -> int:
        """搬自 comprehensive_agent._build_app_score，原样不改。"""
        active_days = int(metrics.get("active_days_30d", 0) or 0)
        consumption_level = str(metrics.get("consumption_ability_level", "low") or "low")
        financial_maturity = str(metrics.get("financial_maturity_level", "unknown") or "unknown")
        score = min(5, max(1, active_days // 8 + 1)) if active_days else 0
        if consumption_level in {"medium", "medium_high", "high"}:
            score = min(5, score + 1)
        if financial_maturity in {"semi_banked", "banked"}:
            score = min(5, score + 1)
        return score

    @staticmethod
    def _build_behavior_score(metrics: dict[str, Any]) -> int:
        """搬自 comprehensive_agent._build_behavior_score，原样不改。"""
        engagement = int(metrics.get("engagement_score", 0) or 0)
        repayment = str(metrics.get("repayment_willingness_level", "medium") or "medium")
        churn = str(metrics.get("churn_risk_level", "medium") or "medium")
        score = min(5, max(1, engagement // 20 + 1)) if engagement else 0
        if repayment in {"high", "medium_high"}:
            score = min(5, score + 1)
        if churn == "high":
            score = max(1, score - 1)
        return score

    @staticmethod
    def _build_credit_score(metrics: dict[str, Any]) -> int:
        """搬自 comprehensive_agent._build_credit_score，原样不改。"""
        risk_level = str(metrics.get("risk_level", "unknown") or "unknown")
        stability = str(metrics.get("credit_stability_level", "unknown") or "unknown")
        score = {"low": 5, "medium": 3, "high": 1}.get(risk_level, 0)
        if stability in {"high", "medium_high"}:
            score = min(5, score + 0)
        if stability == "low" and score > 0:
            score = max(1, score - 1)
        return score
```

> **执行注**：上述 `_build_*_score` 已从 `comprehensive_agent.py` 原样搬运（字段名和计算逻辑完全一致）。
> 若原始文件在执行前已被修改，以执行时的实际文件为准。

**3.4** 更新 `app/runtime_skills/comprehensive/__init__.py`（追加 `ComprehensiveFeatureBuilder`）：

```python
"""Comprehensive profile pipeline (six-step structure)."""
from app.runtime_skills.comprehensive.contracts import (
    ComprehensiveDecisionResult,
    ComprehensiveExplanationResult,
    ComprehensiveFeatureBundle,
    ComprehensivePageResult,
    ComprehensiveRunContext,
    ComprehensiveUpstreamBundle,
    build_comprehensive_run_context,
)
from app.runtime_skills.comprehensive.data_access import (
    ComprehensiveUpstreamProvider,
)
from app.runtime_skills.comprehensive.feature_builder import (
    ComprehensiveFeatureBuilder,
)

__all__ = [
    "ComprehensiveDecisionResult",
    "ComprehensiveExplanationResult",
    "ComprehensiveFeatureBuilder",
    "ComprehensiveFeatureBundle",
    "ComprehensivePageResult",
    "ComprehensiveRunContext",
    "ComprehensiveUpstreamBundle",
    "ComprehensiveUpstreamProvider",
    "build_comprehensive_run_context",
]
```

**3.5** 验证：

```bash
python -m pytest tests/test_comprehensive_phase1.py::TestComprehensiveFeatureBuilder -v
```

预期：`3 passed`。

**3.6** Commit：
```bash
git add app/runtime_skills/comprehensive/ tests/test_comprehensive_phase1.py
git commit -m "feat(comprehensive): add feature builder"
```

---

## Task 4 — decision_engine.py：ComprehensiveDecisionEngine

**目的**：把 if/elif 派生（segment / risk / value / confidence / conflicts / persona_seed / tags_rule）从 `comprehensive_agent.py` 搬出，并提供 `build_prompt_payload`。metrics 拍平成现 schema 形状。

### 文件操作
- **Create** `app/runtime_skills/comprehensive/decision_engine.py`
- **Modify** `app/runtime_skills/comprehensive/__init__.py`（追加导出）
- **Modify** `tests/test_comprehensive_phase1.py`（追加 `TestComprehensiveDecisionEngine`）

### TDD 子步骤

**4.1** 在 `tests/test_comprehensive_phase1.py` 末尾追加测试 class：

```python
from app.runtime_skills.comprehensive import ComprehensiveDecisionEngine


class TestComprehensiveDecisionEngine:
    def setup_method(self) -> None:
        self.builder = ComprehensiveFeatureBuilder()
        self.engine = ComprehensiveDecisionEngine()
        self.context = build_comprehensive_run_context("uid-4")
        self.upstream = _bundle_all_ok("uid-4")
        self.feature = self.builder.build(self.upstream, self.context)

    def test_decision_status_ok_with_full_upstream(self) -> None:
        result = self.engine.decide(self.feature, self.upstream, self.context)
        assert result["decision_status"] == "ok"
        assert result["segment"].startswith("S")
        assert result["overall_risk_level"] in {"low", "medium", "high"}
        assert result["value_signal_level"] in {"low", "medium", "high"}
        assert result["confidence_level"] in {"low", "medium", "high"}

    def test_metrics_flattened_to_schema_shape(self) -> None:
        result = self.engine.decide(self.feature, self.upstream, self.context)
        m = result["metrics"]
        assert "segment" in m
        assert "risk_level" in m
        assert "value_signal_level" in m
        assert "confidence_level" in m
        assert "dimension_scores" in m
        assert "conflict_count" in m

    def test_prompt_payload_keys(self) -> None:
        result = self.engine.decide(self.feature, self.upstream, self.context)
        payload = self.engine.build_prompt_payload(self.feature, result, self.upstream)
        assert "segment" in payload
        assert "missing_modules" in payload
        assert "upstream_summaries" in payload

    def test_partial_upstream_lowers_confidence(self) -> None:
        provider = ComprehensiveUpstreamProvider()
        upstream = provider.fetch(
            "uid-4", self.context,
            app_result={"status": "ok", "structured_result": {"summary": "ok", "metrics": {}}},
            behavior_result={"status": "data_missing", "structured_result": {}},
            credit_result={"status": "data_missing", "structured_result": {}},
        )
        feature = self.builder.build(upstream, self.context)
        result = self.engine.decide(feature, upstream, self.context)
        assert result["confidence_level"] in {"low", "medium"}
```

**4.2** 跑测试，确认失败。

```bash
python -m pytest tests/test_comprehensive_phase1.py::TestComprehensiveDecisionEngine -v
```

**4.3** 写实现。**Create** `app/runtime_skills/comprehensive/decision_engine.py`：

```python
"""Rule-based decision derivation for the comprehensive pipeline."""
from __future__ import annotations

from typing import Any

from app.runtime_skills.comprehensive.contracts import (
    ComprehensiveDecisionResult,
    ComprehensiveFeatureBundle,
    ComprehensiveRunContext,
    ComprehensiveUpstreamBundle,
)


class ComprehensiveDecisionEngine:
    """Rules: segment / risk / value / confidence / conflicts / persona_seed / tags."""

    def decide(
        self,
        feature_bundle: ComprehensiveFeatureBundle,
        upstream: ComprehensiveUpstreamBundle,
        context: ComprehensiveRunContext,
    ) -> ComprehensiveDecisionResult:
        segment = self._assign_segment(feature_bundle)
        risk = self._derive_risk_level(feature_bundle)
        value = self._derive_value_signal(feature_bundle)
        confidence = self._derive_confidence_level(upstream, feature_bundle)
        conflicts = self._build_conflict_explanations(feature_bundle)
        persona_seed = self._build_persona_seed(segment, feature_bundle)
        tags_rule = self._build_tags_seed(feature_bundle, segment, risk)
        flat_metrics = self._flatten_metrics(
            feature_bundle, segment, risk, value, confidence, conflicts,
        )

        return ComprehensiveDecisionResult(
            uid=feature_bundle["uid"],
            country_code=context["country_code"],
            decision_status="ok",
            segment=segment,
            overall_risk_level=risk,
            value_signal_level=value,
            confidence_level=confidence,
            conflict_explanations=conflicts,
            persona_seed=persona_seed,
            tags_rule=tags_rule,
            metrics=flat_metrics,
            errors=[],
        )

    def build_prompt_payload(
        self,
        feature_bundle: ComprehensiveFeatureBundle,
        decision_result: ComprehensiveDecisionResult,
        upstream: ComprehensiveUpstreamBundle,
    ) -> dict[str, Any]:
        return {
            "uid": feature_bundle["uid"],
            "segment": decision_result["segment"],
            "overall_risk_level": decision_result["overall_risk_level"],
            "value_signal_level": decision_result["value_signal_level"],
            "confidence_level": decision_result["confidence_level"],
            "dimension_scores": {
                "app": feature_bundle["app_score"],
                "behavior": feature_bundle["behavior_score"],
                "credit": feature_bundle["credit_score"],
            },
            "conflict_seed": decision_result["conflict_explanations"],
            "persona_seed": decision_result["persona_seed"],
            "tags_rule": decision_result["tags_rule"],
            "upstream_summaries": feature_bundle["upstream_summaries"],
            "missing_modules": upstream["missing_modules"],
        }

    # --- private rule helpers (搬自原 comprehensive_agent.py) ---

    @staticmethod
    def _assign_segment(f: ComprehensiveFeatureBundle) -> str:
        a, b, c = f["app_score"], f["behavior_score"], f["credit_score"]
        avg = (a + b + c) / 3 if (a or b or c) else 0
        if c >= 4 and avg >= 3.5:
            return "S1"
        if avg >= 3.5:
            return "S2"
        if c <= 2 and a >= 3:
            return "S3"
        if b >= 4 and c <= 3:
            return "S4"
        if avg <= 2:
            return "S5"
        return "S6"

    @staticmethod
    def _derive_risk_level(f: ComprehensiveFeatureBundle) -> str:
        c = f["credit_score"]
        if c >= 4:
            return "low"
        if c >= 3:
            return "medium"
        return "high"

    @staticmethod
    def _derive_value_signal(f: ComprehensiveFeatureBundle) -> str:
        avg = (f["app_score"] + f["behavior_score"] + f["credit_score"]) / 3
        if avg >= 4:
            return "high"
        if avg >= 2.5:
            return "medium"
        return "low"

    @staticmethod
    def _derive_confidence_level(
        u: ComprehensiveUpstreamBundle,
        _f: ComprehensiveFeatureBundle,
    ) -> str:
        if u["ok_count"] == 3:
            return "high"
        if u["ok_count"] == 2:
            return "medium"
        return "low"

    @staticmethod
    def _build_conflict_explanations(f: ComprehensiveFeatureBundle) -> list[str]:
        out: list[str] = []
        if f["credit_score"] >= 4 and f["behavior_score"] <= 2:
            out.append("credit_strong_but_behavior_weak")
        if f["app_score"] >= 4 and f["credit_score"] <= 2:
            out.append("app_rich_but_credit_thin")
        if f["behavior_score"] >= 4 and f["credit_score"] <= 2:
            out.append("behavior_active_but_credit_low")
        return out

    @staticmethod
    def _build_persona_seed(segment: str, _f: ComprehensiveFeatureBundle) -> str:
        return f"segment={segment}"

    @staticmethod
    def _build_tags_seed(
        f: ComprehensiveFeatureBundle, segment: str, risk: str,
    ) -> list[str]:
        tags: list[str] = [f"seg:{segment}", f"risk:{risk}"]
        if f["app_score"] >= 4:
            tags.append("app_rich")
        if f["behavior_score"] >= 4:
            tags.append("behavior_active")
        if f["credit_score"] >= 4:
            tags.append("credit_strong")
        return tags

    @staticmethod
    def _flatten_metrics(
        f: ComprehensiveFeatureBundle,
        segment: str,
        risk: str,
        value: str,
        confidence: str,
        conflicts: list[str],
    ) -> dict[str, Any]:
        return {
            "segment": segment,
            "risk_level": risk,
            "value_signal_level": value,
            "confidence_level": confidence,
            "dimension_scores": {
                "app": f["app_score"],
                "behavior": f["behavior_score"],
                "credit": f["credit_score"],
            },
            "conflict_count": len(conflicts),
        }
```

> **执行注**：上述规则函数体是"骨架兼容版"。**Task 4 执行人必须对照
> `app/runtime_skills/comprehensive_agent.py` 现有 `_assign_segment / _build_conflict_explanations
> / _derive_*` 等同名函数原样搬运**——本 Plan 仅定签名与位置，规则细节以现有实现为准。

**4.4** 更新 `app/runtime_skills/comprehensive/__init__.py`（追加 `ComprehensiveDecisionEngine`，与 Task 3 同样的列表追加方式，不再重写整段，仅在 imports 段加：
```python
from app.runtime_skills.comprehensive.decision_engine import (
    ComprehensiveDecisionEngine,
)
```
并在 `__all__` 中按字母序加入 `"ComprehensiveDecisionEngine"`。

**4.5** 验证：
```bash
python -m pytest tests/test_comprehensive_phase1.py::TestComprehensiveDecisionEngine -v
```

预期：`4 passed`。

**4.6** Commit：
```bash
git add app/runtime_skills/comprehensive/ tests/test_comprehensive_phase1.py
git commit -m "feat(comprehensive): add decision engine"
```

---

## Task 5 — explainer.py：ComprehensiveExplainer + prompt 模板追加一行

**目的**：拼 prompt（含 `missing_modules` 条件渲染）、调 ModelClient、按下标对齐润色 conflict、追加 tags（上限 3）、组装 model_trace。

### 文件操作
- **Create** `app/runtime_skills/comprehensive/explainer.py`
- **Modify** `app/prompts/comprehensive_prompt.md`（在 `## Input` 段尾追加 1 行，条件渲染由代码控制）
- **Modify** `app/runtime_skills/comprehensive/__init__.py`（追加导出）
- **Modify** `tests/test_comprehensive_phase1.py`（追加 `TestComprehensiveExplainer`）

### TDD 子步骤

**5.1** 在 `tests/test_comprehensive_phase1.py` 末尾追加测试 class：

```python
from pathlib import Path
from unittest.mock import MagicMock

from app.runtime_skills.comprehensive import ComprehensiveExplainer


def _mk_mock_client(mode: str = "vertex", payload: dict | None = None, status: str = "ok"):
    """Mock ModelClient that returns dict (matching actual generate_structured interface)."""
    client = MagicMock()
    client.mode = mode
    client.model_name = "gemini-3.1-pro-preview"
    # ModelClient.generate_structured returns dict, not object
    client.generate_structured.return_value = {
        "status": status,
        "structured_result": payload if payload is not None else {},
        "model_name": "gemini-3.1-pro-preview",
        "prompt_preview": "test prompt...",
    }
    return client


class TestComprehensiveExplainer:
    def setup_method(self) -> None:
        self.context = build_comprehensive_run_context("uid-5")
        self.upstream = _bundle_all_ok("uid-5")
        self.feature = ComprehensiveFeatureBuilder().build(self.upstream, self.context)
        self.engine = ComprehensiveDecisionEngine()
        self.decision = self.engine.decide(self.feature, self.upstream, self.context)
        self.payload = self.engine.build_prompt_payload(self.feature, self.decision, self.upstream)
        self.prompt_path = Path("app/prompts/comprehensive_prompt.md")

    def test_mock_mode_skips_llm(self) -> None:
        client = _mk_mock_client(mode="mock")
        explainer = ComprehensiveExplainer(client, self.prompt_path)
        result = explainer.explain(
            "uid-5", self.feature, self.decision, self.upstream, self.payload, self.context,
        )
        assert result["used_llm"] is False
        assert result["explanation_status"] == "skipped"
        client.generate_structured.assert_not_called()

    def test_llm_ok_payload_adopted(self) -> None:
        client = _mk_mock_client(payload={
            "summary": "LLM summary",
            "persona": "LLM persona",
            "tags_addon": ["t1", "t2", "t3", "t4"],
            "conflict_explanations": ["c1 polished"],
            "reasoning_texts": {"app": "r1", "behavior": "r2", "credit": "r3"},
        })
        explainer = ComprehensiveExplainer(client, self.prompt_path)
        result = explainer.explain(
            "uid-5", self.feature, self.decision, self.upstream, self.payload, self.context,
        )
        assert result["used_llm"] is True
        assert result["explanation_status"] == "ok"
        assert result["summary"] == "LLM summary"
        assert len(result["tags_addon"]) <= 3

    def test_empty_payload_marks_model_unavailable(self) -> None:
        client = _mk_mock_client(payload={})
        explainer = ComprehensiveExplainer(client, self.prompt_path)
        result = explainer.explain(
            "uid-5", self.feature, self.decision, self.upstream, self.payload, self.context,
        )
        assert result["explanation_status"] == "model_unavailable"
        assert "empty_explanation_payload" in result["model_trace"]["fallback_reason"]

    def test_conflict_alignment_by_index(self) -> None:
        decision = dict(self.decision)
        decision["conflict_explanations"] = ["seedA", "seedB", "seedC"]
        client = _mk_mock_client(payload={
            "summary": "s", "persona": "p", "tags_addon": [],
            "conflict_explanations": ["only-one"],
            "reasoning_texts": {},
        })
        explainer = ComprehensiveExplainer(client, self.prompt_path)
        result = explainer.explain(
            "uid-5", self.feature, decision, self.upstream, self.payload, self.context,
        )
        assert len(result["conflict_explanations"]) == 3
        assert result["conflict_explanations"][0] == "only-one"
        assert result["conflict_explanations"][1] == "seedB"
        assert result["conflict_explanations"][2] == "seedC"

    def test_missing_modules_renders_in_prompt(self) -> None:
        client = _mk_mock_client(payload={
            "summary": "s", "persona": "p", "tags_addon": [],
            "conflict_explanations": [],
            "reasoning_texts": {},
        })
        explainer = ComprehensiveExplainer(client, self.prompt_path)
        payload_with_missing = dict(self.payload)
        payload_with_missing["missing_modules"] = ["behavior_profile"]
        explainer.explain(
            "uid-5", self.feature, self.decision, self.upstream,
            payload_with_missing, self.context,
        )
        sent_prompt = client.generate_structured.call_args.kwargs.get("prompt") \
            or client.generate_structured.call_args.args[0]
        assert "missing_modules" in sent_prompt
        assert "behavior_profile" in sent_prompt

    def test_missing_modules_empty_omits_line(self) -> None:
        client = _mk_mock_client(payload={
            "summary": "s", "persona": "p", "tags_addon": [],
            "conflict_explanations": [],
            "reasoning_texts": {},
        })
        explainer = ComprehensiveExplainer(client, self.prompt_path)
        payload_no_missing = dict(self.payload)
        payload_no_missing["missing_modules"] = []
        explainer.explain(
            "uid-5", self.feature, self.decision, self.upstream,
            payload_no_missing, self.context,
        )
        sent_prompt = client.generate_structured.call_args.kwargs.get("prompt") \
            or client.generate_structured.call_args.args[0]
        # 条件渲染：空 list 时 missing_modules 行不出现
        assert "- missing_modules:" not in sent_prompt
```

**5.2** 跑测试，确认失败：
```bash
python -m pytest tests/test_comprehensive_phase1.py::TestComprehensiveExplainer -v
```

**5.3** 修改 prompt 模板。在 `app/prompts/comprehensive_prompt.md` 的 `## Input` 段末尾追加占位标记（实际渲染由代码控制，模板里只放注释提示）：

在 `## Input` 段最后一项后，追加一行：
```
{{MISSING_MODULES_LINE}}
```

> 该占位符由 explainer 的 `_build_prompt` 根据 `missing_modules` 是否非空替换为：
> - 非空：`- missing_modules: <comma-separated list>; treat their metrics as absent rather than as low values`
> - 空：替换为空字符串（连同前导换行一起去掉）

**5.4** 写实现。**Create** `app/runtime_skills/comprehensive/explainer.py`：

```python
"""LLM explanation layer for the comprehensive pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.model_client import ModelClient
from app.runtime_skills.comprehensive.contracts import (
    ComprehensiveDecisionResult,
    ComprehensiveExplanationResult,
    ComprehensiveFeatureBundle,
    ComprehensiveRunContext,
    ComprehensiveUpstreamBundle,
)


_TAGS_ADDON_LIMIT = 3
_MISSING_PLACEHOLDER = "{{MISSING_MODULES_LINE}}"


class ComprehensiveExplainer:
    def __init__(self, model_client: ModelClient, prompt_path: Path) -> None:
        self.model_client = model_client
        self.prompt_path = prompt_path
        self._template_cache: str | None = None

    def explain(
        self,
        uid: str,
        feature_bundle: ComprehensiveFeatureBundle,
        decision_result: ComprehensiveDecisionResult,
        upstream: ComprehensiveUpstreamBundle,
        prompt_payload: dict[str, Any],
        context: ComprehensiveRunContext,
    ) -> ComprehensiveExplanationResult:
        seed_conflicts = list(decision_result["conflict_explanations"])

        if self.model_client.mode == "mock":
            return self._build_skipped_result(
                uid, context, decision_result, seed_conflicts,
                fallback_reason="model_mode_mock",
            )

        prompt = self._build_prompt(prompt_payload)
        response = self.model_client.generate_structured(
            skill_name="comprehensive_profile",
            prompt=prompt,
            fallback_result=self._build_fallback_payload(decision_result),
        )

        if response.get("status") != "ok":
            return self._build_unavailable_result(
                uid, context, decision_result, seed_conflicts,
                fallback_reason=str(response.get("status", "model_unavailable")),
                response=response,
            )

        payload = response.get("structured_result", {})
        if not isinstance(payload, dict):
            payload = {}
        if not self._has_meaningful_payload(payload):
            return self._build_unavailable_result(
                uid, context, decision_result, seed_conflicts,
                fallback_reason="empty_explanation_payload",
                response=response,
            )

        try:
            patched_conflicts = self._patch_conflict_explanations(
                seed_conflicts, payload.get("conflict_explanations") or [],
            )
            tags_addon = self._filter_tags_addon(
                payload.get("tags_addon") or [],
                set(decision_result["tags_rule"]),
            )
            summary = str(payload.get("summary") or "")
            persona = str(payload.get("persona") or "")
            reasoning = payload.get("reasoning_texts") or {}
            if not isinstance(reasoning, dict):
                reasoning = {}
            reasoning = {str(k): str(v) for k, v in reasoning.items()}
        except Exception as exc:  # noqa: BLE001
            return self._build_unavailable_result(
                uid, context, decision_result, seed_conflicts,
                fallback_reason=f"schema_validation_failed: {exc}",
                response=response,
            )

        return ComprehensiveExplanationResult(
            uid=uid,
            country_code=context["country_code"],
            explanation_status="ok",
            used_llm=True,
            summary=summary,
            persona=persona,
            tags_addon=tags_addon,
            conflict_explanations=patched_conflicts,
            reasoning_texts=reasoning,
            model_trace=self._build_model_trace(response, fallback_reason=""),
            errors=[],
        )

    # --- prompt construction ---

    def _load_prompt_template(self) -> str:
        if self._template_cache is None:
            self._template_cache = self.prompt_path.read_text(encoding="utf-8")
        return self._template_cache

    def _build_prompt(self, payload: dict[str, Any]) -> str:
        template = self._load_prompt_template()
        missing = payload.get("missing_modules") or []
        if missing:
            line = (
                f"- missing_modules: {', '.join(missing)}; "
                f"treat their metrics as absent rather than as low values"
            )
        else:
            line = ""
        rendered = template.replace(_MISSING_PLACEHOLDER, line)
        # 拼 payload JSON 到模板末尾（与 app_profile explainer 行为对齐）
        return f"{rendered}\n\n## Payload\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```\n"

    # --- alignment helpers ---

    @staticmethod
    def _patch_conflict_explanations(
        seed: list[str], llm_returned: list[str],
    ) -> list[str]:
        out: list[str] = []
        for i, seed_text in enumerate(seed):
            if i < len(llm_returned) and isinstance(llm_returned[i], str) and llm_returned[i].strip():
                out.append(llm_returned[i])
            else:
                out.append(seed_text)
        return out

    @staticmethod
    def _filter_tags_addon(raw: list[Any], rule_set: set[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for t in raw:
            if not isinstance(t, str):
                continue
            t = t.strip()
            if not t or t in rule_set or t in seen:
                continue
            seen.add(t)
            out.append(t)
            if len(out) >= _TAGS_ADDON_LIMIT:
                break
        return out

    @staticmethod
    def _has_meaningful_payload(payload: dict[str, Any]) -> bool:
        if not isinstance(payload, dict) or not payload:
            return False
        keys = ("summary", "persona", "tags_addon", "conflict_explanations", "reasoning_texts")
        return any(payload.get(k) for k in keys)

    # --- result builders ---

    def _build_skipped_result(
        self, uid: str, context: ComprehensiveRunContext,
        decision: ComprehensiveDecisionResult, seed_conflicts: list[str],
        *, fallback_reason: str,
    ) -> ComprehensiveExplanationResult:
        return ComprehensiveExplanationResult(
            uid=uid,
            country_code=context["country_code"],
            explanation_status="skipped",
            used_llm=False,
            summary="",
            persona="",
            tags_addon=[],
            conflict_explanations=list(seed_conflicts),
            reasoning_texts={},
            model_trace=self._build_model_trace(None, fallback_reason=fallback_reason),
            errors=[],
        )

    def _build_unavailable_result(
        self, uid: str, context: ComprehensiveRunContext,
        decision: ComprehensiveDecisionResult, seed_conflicts: list[str],
        *, fallback_reason: str, response: Any,
    ) -> ComprehensiveExplanationResult:
        return ComprehensiveExplanationResult(
            uid=uid,
            country_code=context["country_code"],
            explanation_status="model_unavailable",
            used_llm=True,
            summary="",
            persona="",
            tags_addon=[],
            conflict_explanations=list(seed_conflicts),
            reasoning_texts={},
            model_trace=self._build_model_trace(response, fallback_reason=fallback_reason),
            errors=[fallback_reason],
        )

    def _build_model_trace(\n        self, response: Any, *, fallback_reason: str,\n    ) -> dict[str, Any]:\n        return {\n            \"mode\": self.model_client.mode,\n            \"used_llm\": not fallback_reason,\n            \"model_name\": str(\n                response.get(\"model_name\", self.model_client.model_name)\n                if isinstance(response, dict) else self.model_client.model_name\n            ),\n            \"fallback_reason\": fallback_reason,\n        }\n\n    @staticmethod\n    def _build_fallback_payload(decision_result: ComprehensiveDecisionResult) -> dict[str, Any]:\n        \"\"\"Fallback result passed to ModelClient.generate_structured.\"\"\"\n        return {\n            \"status\": \"ok\",\n            \"summary\": \"\",\n            \"persona\": \"\",\n            \"tags_addon\": [],\n            \"conflict_explanations\": list(decision_result[\"conflict_explanations\"]),\n            \"reasoning_texts\": {},\n        }
```

> **执行注**：`ModelClient.generate_structured` 返回 `dict`（不是对象），签名为
> `generate_structured(skill_name, prompt, fallback_result, response_schema=None) -> dict`。
> 返回 dict 的 key 为 `status` / `structured_result` / `model_name` / `prompt_preview`。
> 上方代码已按此接口修正。若实际接口有变，以 [app/core/model_client.py](../../app/core/model_client.py) 为准。

**5.5** 更新 `app/runtime_skills/comprehensive/__init__.py`：在 imports 段加：
```python
from app.runtime_skills.comprehensive.explainer import ComprehensiveExplainer
```
并在 `__all__` 中加入 `"ComprehensiveExplainer"`。

**5.6** 验证：
```bash
python -m pytest tests/test_comprehensive_phase1.py::TestComprehensiveExplainer -v
```

预期：`6 passed`。

**5.7** Commit：
```bash
git add app/runtime_skills/comprehensive/ app/prompts/comprehensive_prompt.md tests/test_comprehensive_phase1.py
git commit -m "feat(comprehensive): add explainer + prompt missing_modules line"
```

---

## Task 6 — assembler.py：ComprehensivePageAssembler

**目的**：组装最终输出（structured_result + summary + charts + report_markdown），含 schema 校验、tags 最终 dedupe、status 收敛规则、data_missing 路径。

### 文件操作
- **Create** `app/runtime_skills/comprehensive/assembler.py`
- **Modify** `app/runtime_skills/comprehensive/__init__.py`（追加导出）
- **Modify** `tests/test_comprehensive_phase1.py`（追加 `TestComprehensivePageAssembler`）

### TDD 子步骤

**6.1** 在 `tests/test_comprehensive_phase1.py` 末尾追加测试 class：

```python
from app.runtime_skills.comprehensive import ComprehensivePageAssembler


class TestComprehensivePageAssembler:
    def setup_method(self) -> None:
        self.context = build_comprehensive_run_context("uid-6")
        self.upstream = _bundle_all_ok("uid-6")
        self.feature = ComprehensiveFeatureBuilder().build(self.upstream, self.context)
        self.engine = ComprehensiveDecisionEngine()
        self.decision = self.engine.decide(self.feature, self.upstream, self.context)
        self.client = _mk_mock_client(mode="mock")
        self.assembler = ComprehensivePageAssembler(self.client)

    def test_build_missing_output_returns_data_missing(self) -> None:
        provider = ComprehensiveUpstreamProvider()
        bad_upstream = provider.fetch(
            "uid-6", self.context,
            app_result={"status": "data_missing", "structured_result": {}},
            behavior_result={"status": "data_missing", "structured_result": {}},
            credit_result={"status": "data_missing", "structured_result": {}},
        )
        page = self.assembler.build_missing_output("uid-6", self.context, bad_upstream)
        assert page["structured_result"]["status"] == "data_missing"

    def test_build_fallback_structured_has_required_fields(self) -> None:
        fb = self.assembler.build_fallback_structured(
            "uid-6", self.feature, self.decision,
        )
        assert fb["uid"] == "uid-6"
        assert "metrics" in fb
        assert "summary" in fb
        assert "tags" in fb

    def test_assemble_merges_llm_text(self) -> None:
        fb = self.assembler.build_fallback_structured(
            "uid-6", self.feature, self.decision,
        )
        explanation: ComprehensiveExplanationResult = ComprehensiveExplanationResult(
            uid="uid-6",
            country_code=self.context["country_code"],
            explanation_status="ok",
            used_llm=True,
            summary="merged summary",
            persona="merged persona",
            tags_addon=["x_addon"],
            conflict_explanations=[],
            reasoning_texts={"app": "r"},
            model_trace={"mode": "vertex", "fallback_reason": ""},
            errors=[],
        )
        page = self.assembler.assemble("uid-6", fb, explanation)
        assert page["structured_result"]["summary"] == "merged summary"
        assert "x_addon" in page["structured_result"]["tags"]

    def test_tags_final_dedupe(self) -> None:
        fb = self.assembler.build_fallback_structured(
            "uid-6", self.feature, self.decision,
        )
        explanation = ComprehensiveExplanationResult(
            uid="uid-6", country_code=self.context["country_code"],
            explanation_status="ok", used_llm=True,
            summary="s", persona="p",
            tags_addon=fb["tags"][:1],  # 与 rule 重复
            conflict_explanations=[], reasoning_texts={},
            model_trace={"mode": "vertex", "fallback_reason": ""}, errors=[],
        )
        page = self.assembler.assemble("uid-6", fb, explanation)
        tags = page["structured_result"]["tags"]
        assert len(tags) == len(set(tags))
```

**6.2** 跑测试，确认失败：
```bash
python -m pytest tests/test_comprehensive_phase1.py::TestComprehensivePageAssembler -v
```

**6.3** 写实现。**Create** `app/runtime_skills/comprehensive/assembler.py`：

```python
"""Final page assembly for the comprehensive pipeline."""
from __future__ import annotations

from typing import Any

from app.core.model_client import ModelClient
from app.runtime_skills.comprehensive.contracts import (
    ComprehensiveDecisionResult,
    ComprehensiveExplanationResult,
    ComprehensiveFeatureBundle,
    ComprehensivePageResult,
    ComprehensiveRunContext,
    ComprehensiveUpstreamBundle,
)


class ComprehensivePageAssembler:
    """Assembles structured_result / charts / report_markdown for the API layer."""

    def __init__(self, model_client: ModelClient) -> None:
        # 仅读取 mode/model_name 用于 fallback 判断，不调用 generate_structured
        self.model_client = model_client

    # --- public ---

    def build_missing_output(
        self,
        uid: str,
        context: ComprehensiveRunContext,
        upstream: ComprehensiveUpstreamBundle,
    ) -> ComprehensivePageResult:
        structured = {
            "uid": uid,
            "status": "data_missing",
            "country_code": context["country_code"],
            "metrics": {},
            "summary": "Upstream profiles unavailable.",
            "persona": "",
            "tags": [],
            "conflict_explanations": [],
            "reasoning_texts": {},
            "upstream_summaries": {},
            "missing_modules": list(upstream["missing_modules"]),
            "model_trace": {
                "mode": self.model_client.mode,
                "model_name": getattr(self.model_client, "model_name", ""),
                "status": "skipped",
                "elapsed_ms": 0,
                "fallback_reason": "upstream_all_missing",
            },
        }
        return ComprehensivePageResult(
            summary=structured["summary"],
            structured_result=structured,
            charts=[],
            report_markdown=self._render_report(structured),
        )

    def build_fallback_structured(
        self,
        uid: str,
        feature_bundle: ComprehensiveFeatureBundle,
        decision_result: ComprehensiveDecisionResult,
    ) -> dict[str, Any]:
        return {
            "uid": uid,
            "status": "ok",
            "country_code": feature_bundle["country_code"],
            "metrics": dict(decision_result["metrics"]),
            "summary": self._fallback_summary(feature_bundle, decision_result),
            "persona": decision_result["persona_seed"],
            "tags": list(decision_result["tags_rule"]),
            "conflict_explanations": list(decision_result["conflict_explanations"]),
            "reasoning_texts": {},
            "upstream_summaries": dict(feature_bundle["upstream_summaries"]),
            "model_trace": {
                "mode": self.model_client.mode,
                "model_name": getattr(self.model_client, "model_name", ""),
                "status": "skipped",
                "elapsed_ms": 0,
                "fallback_reason": "model_mode_mock" if self.model_client.mode == "mock" else "",
            },
        }

    def assemble(
        self,
        uid: str,
        fallback_structured: dict[str, Any],
        explanation_result: ComprehensiveExplanationResult,
    ) -> ComprehensivePageResult:
        structured = dict(fallback_structured)

        if explanation_result["used_llm"] and explanation_result["explanation_status"] == "ok":
            if explanation_result["summary"]:
                structured["summary"] = explanation_result["summary"]
            if explanation_result["persona"]:
                structured["persona"] = explanation_result["persona"]
            if explanation_result["conflict_explanations"]:
                structured["conflict_explanations"] = list(
                    explanation_result["conflict_explanations"]
                )
            if explanation_result["reasoning_texts"]:
                structured["reasoning_texts"] = dict(explanation_result["reasoning_texts"])

            merged_tags: list[str] = list(structured.get("tags") or [])
            seen = set(merged_tags)
            for t in explanation_result["tags_addon"]:
                if t not in seen:
                    merged_tags.append(t)
                    seen.add(t)
            structured["tags"] = merged_tags

            structured["status"] = "ok"

        elif explanation_result["explanation_status"] == "model_unavailable":
            structured["status"] = "model_unavailable"

        # status="skipped"（mock 模式）保持 fallback 的 status="ok"

        structured["model_trace"] = explanation_result["model_trace"]

        # schema 校验（不强行抛异常，失败时收敛 status）
        try:
            self._validate_against_schema(structured)
        except Exception as exc:  # noqa: BLE001
            structured["status"] = "model_unavailable"
            structured["model_trace"] = dict(structured["model_trace"])
            structured["model_trace"]["fallback_reason"] = f"schema_validation_failed: {exc}"

        return ComprehensivePageResult(
            summary=structured["summary"],
            structured_result=structured,
            charts=self._build_charts(structured),
            report_markdown=self._render_report(structured),
        )

    # --- private ---

    @staticmethod
    def _fallback_summary(
        f: ComprehensiveFeatureBundle, d: ComprehensiveDecisionResult,
    ) -> str:
        return (
            f"Segment {d['segment']}, risk={d['overall_risk_level']}, "
            f"value={d['value_signal_level']}, confidence={d['confidence_level']}."
        )

    @staticmethod
    def _build_charts(structured: dict[str, Any]) -> list[dict[str, Any]]:
        scores = (structured.get("metrics") or {}).get("dimension_scores") or {}
        if not scores:
            return []
        return [{
            "type": "radar",
            "title": "Dimension Scores",
            "data": scores,
        }]

    @staticmethod
    def _render_report(structured: dict[str, Any]) -> str:
        # 与 services.report_renderer 保持兼容；这里仅返回最小 Markdown
        lines = [
            f"# Comprehensive Profile - {structured.get('uid', '')}",
            "",
            f"**Status**: {structured.get('status', '')}",
            f"**Summary**: {structured.get('summary', '')}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _validate_against_schema(structured: dict[str, Any]) -> None:
        # 用现有 Pydantic schema 做校验；schema 不改，仅消费。
        from app.schemas.comprehensive_profile import ComprehensiveProfileStructuredResult
        from app.utils.pydantic_compat import model_validate_compat
        model_validate_compat(ComprehensiveProfileStructuredResult, structured)
```

> **执行注**：实际 `ComprehensiveProfileStructuredResult` 类名/方法以
> [app/schemas/comprehensive_profile.py](../../app/schemas/comprehensive_profile.py) 为准
> （Pydantic v1 用 `parse_obj`，v2 用 `model_validate`）；按现有版本调整。

**6.4** 更新 `app/runtime_skills/comprehensive/__init__.py`：在 imports 段加：
```python
from app.runtime_skills.comprehensive.assembler import ComprehensivePageAssembler
```
并在 `__all__` 中加入 `"ComprehensivePageAssembler"`。此时 `__all__` 应包含 6 个 TypedDict + `build_comprehensive_run_context` + 5 个 class（Provider / FeatureBuilder / DecisionEngine / Explainer / PageAssembler）共 12 项导出。

**6.5** 验证：
```bash
python -m pytest tests/test_comprehensive_phase1.py::TestComprehensivePageAssembler -v
```

预期：`4 passed`。

**6.6** Commit：
```bash
git add app/runtime_skills/comprehensive/ tests/test_comprehensive_phase1.py
git commit -m "feat(comprehensive): add page assembler"
```

---

## Task 7 — 重写 comprehensive_agent.py 为薄入口 + E2E + 收尾

**目的**：把 `comprehensive_agent.py` 改为 ≤ 80 行的薄入口，跑 E2E + 全量回归，更新 PLANNING.md / TASK.md，打 complete commit。

### 文件操作
- **Modify** `app/runtime_skills/comprehensive_agent.py`（重写）
- **Modify** `tests/test_comprehensive_phase1.py`（追加 `TestComprehensiveAgentE2E`）
- **Modify** `PLANNING.md`（把 ⚠️ comprehensive_agent.py 标记改为 ✅，并补 `comprehensive/` 子目录条目）
- **Modify** `TASK.md`（把 P1 拆分 Comprehensive 那行勾掉 / 移到"已完成"区）

### TDD 子步骤

**7.1** 在 `tests/test_comprehensive_phase1.py` 末尾追加 E2E 测试 class：

```python
from app.runtime_skills.comprehensive_agent import ComprehensiveProfileSkill


class TestComprehensiveAgentE2E:
    def setup_method(self) -> None:
        self.client = _mk_mock_client(mode="mock")
        self.skill = ComprehensiveProfileSkill(self.client)

    def test_data_missing_path(self) -> None:
        result = self.skill.analyze(
            "uid-7",
            app_profile_result={"status": "data_missing", "structured_result": {}},
            behavior_profile_result={"status": "data_missing", "structured_result": {}},
            credit_profile_result={"status": "data_missing", "structured_result": {}},
        )
        assert result["structured_result"]["status"] == "data_missing"

    def test_partial_upstream_mock_mode_ok(self) -> None:
        result = self.skill.analyze(
            "uid-7",
            app_profile_result={"status": "ok", "structured_result": {
                "summary": "ok", "metrics": {"installed_app_count": 30}}},
            behavior_profile_result={"status": "data_missing", "structured_result": {}},
            credit_profile_result={"status": "ok", "structured_result": {
                "summary": "ok", "metrics": {"credit_score": 720}}},
        )
        assert result["structured_result"]["status"] == "ok"
        assert "behavior_profile" in result["structured_result"]["missing_modules"]

    def test_full_upstream_mock_mode_ok(self) -> None:
        result = self.skill.analyze(
            "uid-7",
            app_profile_result={"status": "ok", "structured_result": {
                "summary": "ok", "metrics": {"installed_app_count": 42}}},
            behavior_profile_result={"status": "ok", "structured_result": {
                "summary": "ok", "metrics": {"event_count_30d": 200}}},
            credit_profile_result={"status": "ok", "structured_result": {
                "summary": "ok", "metrics": {"credit_score": 720}}},
        )
        assert result["structured_result"]["status"] == "ok"
        # 顶层键集合稳定（与重构前保持兼容）
        assert set(result.keys()) >= {"summary", "structured_result", "charts", "report_markdown"}
```

**7.2** 跑 E2E，确认失败（旧 `ComprehensiveProfileSkill` 仍是 512 行的版本，但导入路径不变 → 应该能跑，需先改实现才能新测全过；先确认改前测试结果）：
```bash
python -m pytest tests/test_comprehensive_phase1.py::TestComprehensiveAgentE2E -v
```

**7.3** 重写 `app/runtime_skills/comprehensive_agent.py`：

```python
"""ComprehensiveProfileSkill — six-step pipeline orchestrator (thin entry)."""
from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.model_client import ModelClient
from app.runtime_skills.base import BaseSkill
from app.runtime_skills.comprehensive import (
    ComprehensiveDecisionEngine,
    ComprehensiveExplainer,
    ComprehensiveFeatureBuilder,
    ComprehensivePageAssembler,
    ComprehensiveUpstreamProvider,
    build_comprehensive_run_context,
)


class ComprehensiveProfileSkill(BaseSkill):
    name = "comprehensive_profile"
    stage = 1
    depends_on: list[str] = ["app_profile", "behavior_profile", "credit_profile"]

    def __init__(self, model_client: ModelClient) -> None:
        self.model_client = model_client
        prompt_path = settings.resolve_path(
            f"{settings.prompt_dir}/comprehensive_prompt.md"
        )
        self.upstream_provider = ComprehensiveUpstreamProvider()
        self.feature_builder = ComprehensiveFeatureBuilder()
        self.decision_engine = ComprehensiveDecisionEngine()
        self.explainer = ComprehensiveExplainer(model_client, prompt_path)
        self.assembler = ComprehensivePageAssembler(model_client)

    def analyze(self, uid: str, **kwargs: Any) -> dict[str, Any]:
        context = build_comprehensive_run_context(
            uid, application_time=kwargs.get("application_time"),
        )
        upstream = self.upstream_provider.fetch(
            uid, context,
            app_result=kwargs.get("app_profile_result", {}),
            behavior_result=kwargs.get("behavior_profile_result", {}),
            credit_result=kwargs.get("credit_profile_result", {}),
        )
        if upstream["data_status"] != "ok":
            return self.assembler.build_missing_output(uid, context, upstream)

        feature_bundle = self.feature_builder.build(upstream, context)
        decision_result = self.decision_engine.decide(feature_bundle, upstream, context)
        prompt_payload = self.decision_engine.build_prompt_payload(
            feature_bundle, decision_result, upstream,
        )
        fallback_structured = self.assembler.build_fallback_structured(
            uid, feature_bundle, decision_result,
        )
        explanation_result = self.explainer.explain(
            uid, feature_bundle, decision_result, upstream,
            prompt_payload, context,
        )
        return self.assembler.assemble(uid, fallback_structured, explanation_result)
```

**7.4** 验证薄入口行数：
```bash
python -c "import pathlib; n = sum(1 for _ in pathlib.Path('app/runtime_skills/comprehensive_agent.py').open(encoding='utf-8')); print('lines=', n); assert n <= 80, f'too long: {n}'"
```

预期输出：`lines= <某个 ≤ 80 的整数>`。

**7.5** 跑 E2E + 全量回归：
```bash
python -m pytest tests/test_comprehensive_phase1.py -v
python -m pytest tests/ -v
```

预期：
- `tests/test_comprehensive_phase1.py` 至少 18 测试全过（6 contracts + 4 provider + 3 feature + 4 decision + 6 explainer + 4 assembler + 3 e2e ≥ 18，按设计文档第 9 章 ≥ 18 要求）
- 全量 `pytest tests/ -v` 报 ≥ 86 passed（68 基线 + ≥ 18 新增）

**7.6** 更新 PLANNING.md：
- 把第 41 行 `comprehensive_agent.py    ⚠️ ...` 改为 `comprehensive_agent.py    ✅ 薄入口（≤ 80 行）`
- 在其下方追加：
  ```
  │   │   └── comprehensive/                ✅ 六步管线（结构与 app_profile 对齐）
  ```

**7.7** 更新 TASK.md：
- 把 `- [ ] P1: 拆分 Comprehensive 为六步管线 →（待写 Plan）` 改为 `- [x] P1: 拆分 Comprehensive 为六步管线 → 完成（2026-04-28，docs/plans/comprehensive-refactor-plan.md）`
- 在"开发中发现"中删除第一条（"comprehensive_agent.py 单文件 512 行..."）

**7.8** Commit + 打 complete：
```bash
git add app/runtime_skills/comprehensive_agent.py tests/test_comprehensive_phase1.py PLANNING.md TASK.md
git commit -m "feat(comprehensive): rewrite agent as thin entry + e2e tests"
git commit --allow-empty -m "[complete] comprehensive-refactor"
```

**7.9** 最终验证：
```bash
git log --oneline -5
python -m pytest tests/ -v --tb=short
```

预期：
- `git log` 顶部有 `[complete] comprehensive-refactor`
- 全量测试 ≥ 86 passed

---

## 完工验收清单（来自设计文档第 9 章）

- [ ] `app/runtime_skills/comprehensive/` 下六个文件齐全（contracts / data_access / feature_builder / decision_engine / explainer / assembler），每个文件单一职责
- [ ] `comprehensive_agent.py` 行数 ≤ 80
- [ ] `tests/test_comprehensive_phase1.py` 至少覆盖 6 个 class、每个 class ≥ 3 个测试用例
- [ ] `pytest tests/ -v` 通过（基线 68 + 新增 comprehensive_phase1 ≥ 18 → 共 ≥ 86 全过）
- [ ] `ComprehensiveProfileStructuredResult` schema 未改
- [ ] `BaseSkill.analyze(uid, **kwargs)` 签名未改
- [ ] `app/prompts/comprehensive_prompt.md` 仅追加一行 `missing_modules`（条件渲染）
- [ ] mock 模式下端到端可跑通（`MODEL_MODE=mock`）
- [ ] `POST /api/analyze` 的响应 JSON 形状未改（顶层键集合与重构前一致）

---

## 备注

- **执行节奏**：每个 Task 完成后停下汇报，等用户确认再进下一个 Task。Task 0/7 是边界仪式，必须严格按顺序。
- **代码搬运纪律**：Task 3、4 的规则函数体（`_build_*_score`、`_assign_segment`、`_build_conflict_explanations`、`_derive_*`）以原 `comprehensive_agent.py` 实现为准，本 Plan 给的是骨架兼容版，仅定签名与位置。规则细节如有不一致，**以现有实现为准**。
- **`__init__.py` 渐进式更新**：Task 1 导出 contracts；Task 2-6 每实现一个文件就在 `__init__.py` 增加对应 class 导出；Task 7 时 `__init__.py` 应已有完整的 5 个 class + 6 个 TypedDict + 1 个工厂函数共 12 项导出。
- **不 push**：本 Plan 仅本地 commit，不推送 remote。
