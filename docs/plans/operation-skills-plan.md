# Operation Skills 实现 Plan — ProductAdviceSkill + OpsAdviceSkill

- 关联 Design Doc：[docs/specs/operation-skills-design.md](../specs/operation-skills-design.md)
- baseline commit：`7d7483c [baseline] operation-skills: design doc + stage=2 skeleton`
- 写作日期：2026-04-30
- 状态：待审核（不 commit，等用户确认）

---

## 0. Scope / Out of Scope

### Scope
- 实现 ProductAdviceSkill 与 OpsAdviceSkill 的六步管线（共 10 个子文件）
- 填充 `app/country_packs/mx/{product_advice_rules.py, ops_advice_rules.py}` 的 S1–S6 矩阵
- 改写 `*_advice_agent.py` 入口为薄编排（≤ 80 行）
- 新增 2 个 Prompt 模板
- 新增 2 个 phase1 测试 + 1 个 orchestrator 集成测试
- mock 模式 deterministic 输出 100% 由规则驱动
- 上游缺失/无效时降级为 `data_missing`
- 全量 pytest 维持 0 failed

### Out of Scope（本期不做）
- 真实 LLM 联调（mock 模式覆盖即可，real LLM 留作 V1 follow-up）
- charts 渲染（`charts: []` 留空）
- 多国家（仅 mx；其他国家走 country_pack 占位）
- LangGraph 迁移
- Prompt A/B / 命中率监控

---

## 1. 总体策略

| Phase | 主题 | Tasks | 预估 |
|---|---|---|---|
| Phase A | country_packs 矩阵填充 | A.1, A.2 | 6 min |
| Phase B | ProductAdvice 六步管线（TDD） | B.1 → B.6 | 25 min |
| Phase C | OpsAdvice 六步管线（TDD） | C.1 → C.6 | 25 min |
| Phase D | 编排接线 + 集成测试 | D.1, D.2 | 10 min |
| Phase E | 收尾（TASK.md / [complete] commit） | E.1 | 3 min |

**TDD 节奏（每个 Task 内）**：写测试 → `pytest -k` 看红 → 写实现 → `pytest -k` 看绿 → `git add && git commit`。

**单 Task 控制**：每个 Task ≤ 5 分钟，文件路径精确，验证命令明确。

---

## 2. Worked Example（端到端输入 / 输出）

### 输入：comprehensive_profile_result（已序列化为 dict）

```python
comprehensive_profile_result = {
    "summary": "...",
    "structured_result": {
        "agent_name": "comprehensive_profile_agent",
        "uid": "MX_USER_78432",
        "status": "ok",
        "persona": "S2 稳健经营客",
        "metrics": {
            "recommended_segment": "S2",
            "segment_name": "稳健经营客",
            "overall_risk": "中低",
            "overall_value": "中高",
            "behavior_tags": {
                "churn_risk": "低",
                "best_contact_channel": "WhatsApp",
                "best_contact_time": "晚间19-21点",
                "product_activity": "★★★★☆ 较高",
            },
            "financial_tags": {
                "multi_head_risk": "中",
                "debt_pressure": "中",
                "borrowing_urgency": "高",
            },
            "confidence": "高",
            "data_completeness": {"skill1_available": True, "skill2_available": True, "skill3_available": True},
        },
        "tags": ["S2", "稳健经营客", "WhatsApp"],
        "model_trace": {"mode": "mock", "used_llm": False, "model_name": "", "fallback_reason": "model_mode_mock"},
    },
    "charts": [],
    "report_markdown": "...",
}
```

### 输出：ProductAdviceSkill.analyze(uid="MX_USER_78432", comprehensive_profile_result=...) → AgentOutput dict

```python
{
    "summary": "S2 稳健经营客建议续贷优惠 + 适度提额（10-20%），WhatsApp 触达。",
    "structured_result": {
        "agent_name": "product_advice_agent",
        "uid": "MX_USER_78432",
        "status": "ok",
        "segment": "S2",
        "segment_name": "稳健经营客",
        "renewal_strategy": {"action": "续贷优惠", "trigger_offset_days": -3, "reason": "稳健客群满期前 3 天触达"},
        "credit_line_action": {"action": "适度提额", "delta_pct_range": [10, 20], "reason": "信用稳定，多头中风险"},
        "rate_plan": {"plan": "标准利率 + 优惠券", "anchor_competitor": None},
        "recommended_channel": {"primary": "WhatsApp", "secondary": None, "best_time": "晚间19-21点"},
        "priority": "P1",
        "tags": ["S2", "续贷优惠", "适度提额", "WhatsApp"],
        "explanation": {},
        "model_trace": {"mode": "mock", "used_llm": False, "model_name": "...", "fallback_reason": "model_mode_mock"},
    },
    "charts": [],
    "report_markdown": "## S2 稳健经营客 · 产品策略建议\n...",
}
```

### 输出：OpsAdviceSkill.analyze(uid, comprehensive_profile_result=...) → AgentOutput dict（结构对称）

OpsAdvice 在同一上游下输出 collection_strategy=T+1 软提醒、churn_warning=无（churn_risk=低）、outreach_channel=WhatsApp、retention_offer=空。

---

## 3. 风险表

| 风险 | 影响 | 缓解 |
|---|---|---|
| comprehensive_profile_result 字段嵌套不稳定（`metrics.recommended_segment` vs 顶层） | 上游契约误读 → 全部走 data_missing | data_access 层兜底两路读取（先 metrics 后顶层），写测试覆盖 |
| segment 大小写 / 空格 | 矩阵 miss → data_missing | feature_builder normalize：`upper().strip()` |
| `comprehensive_profile_result.structured_result` 为空 dict | KeyError | 全程用 `dict.get(..., default)` |
| Mock LLM 时 explainer 误调真实模型 | 测试不稳定 | explainer 第一行检查 `model_client.mode == "mock"` 直接跳过 |
| 新增字段使现有 `UserAnalysisResult` 反序列化报错 | 全量回归挂 | Optional + None 默认（已在 Step 3 落地，278 passed 验证过） |
| Pydantic v2 ignore extra 行为变更 | 旧 client 反序列化新 schema | 不依赖；只用 Optional 字段保证兼容 |
| churn_risk 等级提升把 S1 拉到 S5 | 业务错误 | 提升只动 churn_warning.level，不动 collection_strategy 强度 |

---

## 4. Phase A — country_packs 矩阵填充

### Task A.1 — 填充 MX_PRODUCT_ADVICE_RULES

**Files**
- Modify：`app/country_packs/mx/product_advice_rules.py`
- Test：`tests/test_product_advice_rules.py`（新建）

**TDD step 1**：写测试

```python
# tests/test_product_advice_rules.py
from app.country_packs.mx.product_advice_rules import MX_PRODUCT_ADVICE_RULES
from app.country_packs.mx.segments import MX_SEGMENTS


def test_all_six_segments_present():
    assert set(MX_PRODUCT_ADVICE_RULES.keys()) == set(MX_SEGMENTS)


def test_each_segment_has_required_keys():
    required = {"renewal_strategy", "credit_line_action", "rate_plan",
                "recommended_channel", "priority", "tags"}
    for seg, rule in MX_PRODUCT_ADVICE_RULES.items():
        assert required.issubset(rule.keys()), f"{seg} missing keys"


def test_s5_no_proactive_renewal():
    s5 = MX_PRODUCT_ADVICE_RULES["S5"]
    assert "不主动" in s5["renewal_strategy"]["action"]
    assert s5["credit_line_action"]["action"] == "控额"
    assert s5["credit_line_action"]["delta_pct_range"] is None


def test_s1_proactive_credit_increase():
    s1 = MX_PRODUCT_ADVICE_RULES["S1"]
    assert s1["credit_line_action"]["action"] == "主动提额"
    lo, hi = s1["credit_line_action"]["delta_pct_range"]
    assert lo == 30 and hi == 50
```

**Verify red**：`python -m pytest tests/test_product_advice_rules.py -v` → 4 failed (空 dict)

**TDD step 2**：实现

```python
# app/country_packs/mx/product_advice_rules.py
"""Mexico Product Advice country pack — S1-S6 strategy table."""

from __future__ import annotations

from typing import Any, Final

MX_PRODUCT_ADVICE_RULES: Final[dict[str, dict[str, Any]]] = {
    "S1": {
        "renewal_strategy": {"action": "主动续贷", "trigger_offset_days": -7, "reason": "优质客群提前 7 天触达"},
        "credit_line_action": {"action": "主动提额", "delta_pct_range": (30, 50), "reason": "高价值低风险，VIP 提额"},
        "rate_plan": {"plan": "VIP 专属低利率", "anchor_competitor": None},
        "recommended_channel": {"primary": "WhatsApp", "secondary": "Push"},
        "priority": "P0",
        "tags": ["S1", "主动续贷", "主动提额", "VIP"],
    },
    "S2": {
        "renewal_strategy": {"action": "续贷优惠", "trigger_offset_days": -3, "reason": "稳健客群满期前 3 天触达"},
        "credit_line_action": {"action": "适度提额", "delta_pct_range": (10, 20), "reason": "信用稳定，适度上调"},
        "rate_plan": {"plan": "标准利率 + 优惠券", "anchor_competitor": None},
        "recommended_channel": {"primary": "WhatsApp", "secondary": None},
        "priority": "P1",
        "tags": ["S2", "续贷优惠", "适度提额", "WhatsApp"],
    },
    "S3": {
        "renewal_strategy": {"action": "限时利率优惠续贷", "trigger_offset_days": -5, "reason": "价格敏感客群比价中"},
        "credit_line_action": {"action": "维持额度", "delta_pct_range": None, "reason": "比价中不刺激额度"},
        "rate_plan": {"plan": "比竞品低", "anchor_competitor": "Kueski"},
        "recommended_channel": {"primary": "Push", "secondary": "Email"},
        "priority": "P1",
        "tags": ["S3", "限时优惠", "比价锚点", "Push"],
    },
    "S4": {
        "renewal_strategy": {"action": "挽回式续贷", "trigger_offset_days": -10, "reason": "潜在流失需提前挽回"},
        "credit_line_action": {"action": "维持额度", "delta_pct_range": None, "reason": "活跃下降不动额度"},
        "rate_plan": {"plan": "挽回券（首期免息）", "anchor_competitor": None},
        "recommended_channel": {"primary": "WhatsApp", "secondary": None},
        "priority": "P0",
        "tags": ["S4", "挽回续贷", "首期免息", "WhatsApp 专属关怀"],
    },
    "S5": {
        "renewal_strategy": {"action": "不主动续贷 / 缩短账期", "trigger_offset_days": 0, "reason": "多头高风险不主动"},
        "credit_line_action": {"action": "控额", "delta_pct_range": None, "reason": "多头借贷需控风险敞口"},
        "rate_plan": {"plan": "不发券", "anchor_competitor": None},
        "recommended_channel": {"primary": "SMS", "secondary": None},
        "priority": "—",
        "tags": ["S5", "不主动续贷", "控额", "风控通知"],
    },
    "S6": {
        "renewal_strategy": {"action": "场景化续贷（Buen Fin 唤醒）", "trigger_offset_days": -14, "reason": "沉默客群场景唤醒"},
        "credit_line_action": {"action": "维持额度", "delta_pct_range": None, "reason": "无明确意图"},
        "rate_plan": {"plan": "标准利率", "anchor_competitor": None},
        "recommended_channel": {"primary": "Push", "secondary": None},
        "priority": "P2",
        "tags": ["S6", "场景化", "Buen Fin", "轻触达"],
    },
}
```

**Verify green**：`python -m pytest tests/test_product_advice_rules.py -v` → **4 passed**

**Commit**：`feat(skills): MX product advice S1-S6 rules table`

---

### Task A.2 — 填充 MX_OPS_ADVICE_RULES

**Files**
- Modify：`app/country_packs/mx/ops_advice_rules.py`
- Test：`tests/test_ops_advice_rules.py`（新建）

**TDD step 1**：写测试

```python
# tests/test_ops_advice_rules.py
from app.country_packs.mx.ops_advice_rules import MX_OPS_ADVICE_RULES
from app.country_packs.mx.segments import MX_SEGMENTS


def test_all_six_segments_present():
    assert set(MX_OPS_ADVICE_RULES.keys()) == set(MX_SEGMENTS)


def test_each_segment_has_required_keys():
    required = {"collection_strategy", "churn_warning", "outreach_channel",
                "retention_offer", "tags"}
    for seg, rule in MX_OPS_ADVICE_RULES.items():
        assert required.issubset(rule.keys()), f"{seg} missing keys"


def test_s4_strong_churn_warning():
    s4 = MX_OPS_ADVICE_RULES["S4"]
    assert s4["churn_warning"]["level"] == "强"
    assert s4["retention_offer"]["type"] is not None


def test_s5_no_offer():
    s5 = MX_OPS_ADVICE_RULES["S5"]
    assert s5["retention_offer"]["type"] is None
    assert s5["collection_strategy"]["intensity"] == "strong"
```

**Verify red**：`python -m pytest tests/test_ops_advice_rules.py -v` → 4 failed

**TDD step 2**：实现

```python
# app/country_packs/mx/ops_advice_rules.py
"""Mexico Ops Advice country pack — S1-S6 strategy table."""

from __future__ import annotations

from typing import Any, Final

MX_OPS_ADVICE_RULES: Final[dict[str, dict[str, Any]]] = {
    "S1": {
        "collection_strategy": {"trigger": "无", "reminder_steps": [], "intensity": "none"},
        "churn_warning": {"level": "无", "signals": []},
        "outreach_channel": {"primary": "—", "best_time": ""},
        "retention_offer": {"type": None, "valid_days": None},
        "tags": ["S1", "无需催收"],
    },
    "S2": {
        "collection_strategy": {"trigger": "T+1", "reminder_steps": ["WhatsApp soft"], "intensity": "soft"},
        "churn_warning": {"level": "无", "signals": []},
        "outreach_channel": {"primary": "WhatsApp", "best_time": "晚间19-21点"},
        "retention_offer": {"type": None, "valid_days": None},
        "tags": ["S2", "T+1 软提醒", "WhatsApp"],
    },
    "S3": {
        "collection_strategy": {"trigger": "T+1", "reminder_steps": ["Push soft"], "intensity": "soft"},
        "churn_warning": {"level": "轻", "signals": ["竞品APP安装", "比价行为"]},
        "outreach_channel": {"primary": "Push", "best_time": "晚间19-21点"},
        "retention_offer": {"type": "利率券", "valid_days": 14},
        "tags": ["S3", "轻流失预警", "利率券"],
    },
    "S4": {
        "collection_strategy": {"trigger": "T+1", "reminder_steps": ["WhatsApp soft", "WhatsApp + Push D+3"], "intensity": "soft"},
        "churn_warning": {"level": "强", "signals": ["竞品APP安装", "活跃度下降"]},
        "outreach_channel": {"primary": "WhatsApp", "best_time": "晚间19-21点"},
        "retention_offer": {"type": "首期免息+挽回礼包", "valid_days": 14},
        "tags": ["S4", "强流失预警", "WhatsApp", "挽回礼包"],
    },
    "S5": {
        "collection_strategy": {"trigger": "D-3", "reminder_steps": ["SMS D-3", "Phone T+1", "Phone T+7"], "intensity": "strong"},
        "churn_warning": {"level": "强", "signals": ["多头借贷", "高负债"]},
        "outreach_channel": {"primary": "SMS+Phone", "best_time": "工作日10-18点"},
        "retention_offer": {"type": None, "valid_days": None},
        "tags": ["S5", "提前提醒", "SMS+Phone", "强催收"],
    },
    "S6": {
        "collection_strategy": {"trigger": "T+1", "reminder_steps": ["Push light"], "intensity": "soft"},
        "churn_warning": {"level": "中", "signals": ["沉默 30 天"]},
        "outreach_channel": {"primary": "Push", "best_time": "晚间19-21点"},
        "retention_offer": {"type": "唤醒券", "valid_days": 30},
        "tags": ["S6", "中预警", "唤醒券", "轻触达"],
    },
}
```

**Verify green**：`python -m pytest tests/test_ops_advice_rules.py -v` → **4 passed**

**Commit**：`feat(skills): MX ops advice S1-S6 rules table`

---

## 5. Phase B — ProductAdvice 六步管线（TDD）

### Task B.1 — contracts 已就位 / 新增 build_run_context 函数

**Files**
- Modify：`app/runtime_skills/product_advice/contracts.py`（追加 `build_product_advice_run_context`）
- Modify：`app/runtime_skills/product_advice/__init__.py`（re-export）

**TDD step 1**：写测试（合并到下一 Task 的 phase1 测试中，本 Task 不单独跑）

**实现**（追加到现有 contracts.py 末尾）：

```python
from datetime import datetime, timezone


def build_product_advice_run_context(
    uid: str,
    *,
    trace_id: str = "",
    channel: str = "api",
) -> ProductAdviceRunContext:
    return {"uid": uid, "trace_id": trace_id, "channel": channel or "api"}
```

`__init__.py` 末尾 `__all__` 列表追加 `"build_product_advice_run_context"` 并 import。

**Verify**：`python -c "from app.runtime_skills.product_advice import build_product_advice_run_context; print(build_product_advice_run_context('U1'))"` → `{'uid': 'U1', 'trace_id': '', 'channel': 'api'}`

**Commit**：`feat(skills): product_advice run-context builder`

---

### Task B.2 — data_access：从 comprehensive_profile_result 抽字段

**Files**
- Modify：`app/runtime_skills/product_advice/data_access.py`
- Test：`tests/test_product_advice_phase1.py`（新建，本 Task 写第一组）

**TDD step 1**：写测试

```python
# tests/test_product_advice_phase1.py（节选 — Task B.2 部分）
import unittest
from app.runtime_skills.product_advice.contracts import build_product_advice_run_context
from app.runtime_skills.product_advice.data_access import ProductAdviceUpstreamProvider


def _comp_result(segment="S2", overall_risk="中低", overall_value="中高", churn="低", status="ok"):
    return {
        "structured_result": {
            "uid": "U1",
            "status": status,
            "metrics": {
                "recommended_segment": segment,
                "segment_name": "稳健经营客",
                "overall_risk": overall_risk,
                "overall_value": overall_value,
                "behavior_tags": {"churn_risk": churn, "best_contact_channel": "WhatsApp",
                                  "best_contact_time": "晚间19-21点", "product_activity": "★★★★☆"},
                "financial_tags": {"multi_head_risk": "中", "debt_pressure": "中", "borrowing_urgency": "高"},
                "confidence": "高",
                "data_completeness": {"skill1_available": True, "skill2_available": True, "skill3_available": True},
            },
        },
    }


class ProductAdviceDataAccessTests(unittest.TestCase):
    def test_fetch_happy(self):
        ctx = build_product_advice_run_context("U1")
        bundle = ProductAdviceUpstreamProvider().fetch("U1", ctx, comprehensive_result=_comp_result())
        self.assertEqual(bundle["data_status"], "ok")
        self.assertEqual(bundle["segment"], "S2")
        self.assertEqual(bundle["behavior_tags"]["churn_risk"], "低")

    def test_fetch_missing_when_empty(self):
        ctx = build_product_advice_run_context("U1")
        bundle = ProductAdviceUpstreamProvider().fetch("U1", ctx, comprehensive_result={})
        self.assertEqual(bundle["data_status"], "missing")

    def test_fetch_missing_when_status_not_ok(self):
        ctx = build_product_advice_run_context("U1")
        bundle = ProductAdviceUpstreamProvider().fetch("U1", ctx, comprehensive_result=_comp_result(status="data_missing"))
        self.assertEqual(bundle["data_status"], "missing")

    def test_fetch_missing_when_segment_invalid(self):
        ctx = build_product_advice_run_context("U1")
        bundle = ProductAdviceUpstreamProvider().fetch("U1", ctx, comprehensive_result=_comp_result(segment="X9"))
        self.assertEqual(bundle["data_status"], "invalid_segment")
```

**Verify red**：`python -m pytest tests/test_product_advice_phase1.py -v -k DataAccess` → 4 failed (NotImplementedError)

**TDD step 2**：实现

```python
# app/runtime_skills/product_advice/data_access.py
"""Data access layer for the Product Advice pipeline."""

from __future__ import annotations

from typing import Any

from app.country_packs.mx.segments import MX_SEGMENTS
from app.runtime_skills.product_advice.contracts import (
    ProductAdviceRunContext,
    ProductAdviceUpstreamBundle,
)


class ProductAdviceUpstreamProvider:
    def fetch(
        self,
        uid: str,
        context: ProductAdviceRunContext,
        *,
        comprehensive_result: dict[str, Any],
    ) -> ProductAdviceUpstreamBundle:
        sr = comprehensive_result.get("structured_result", {}) if isinstance(comprehensive_result, dict) else {}
        if not isinstance(sr, dict) or not sr:
            return self._missing(uid, "missing")
        if str(sr.get("status", "")) != "ok":
            return self._missing(uid, "missing")

        metrics = sr.get("metrics", {}) if isinstance(sr.get("metrics"), dict) else {}
        segment_raw = str(metrics.get("recommended_segment") or sr.get("recommended_segment") or "").strip().upper()
        segment_name = str(metrics.get("segment_name") or sr.get("segment_name") or "")

        if segment_raw not in MX_SEGMENTS:
            return self._missing(uid, "invalid_segment", segment=segment_raw)

        behavior_tags = metrics.get("behavior_tags", {}) if isinstance(metrics.get("behavior_tags"), dict) else {}
        financial_tags = metrics.get("financial_tags", {}) if isinstance(metrics.get("financial_tags"), dict) else {}

        return {
            "data_status": "ok",
            "segment": segment_raw,
            "segment_name": segment_name,
            "overall_risk": str(metrics.get("overall_risk", "")),
            "overall_value": str(metrics.get("overall_value", "")),
            "behavior_tags": dict(behavior_tags),
            "financial_tags": dict(financial_tags),
            "confidence": str(metrics.get("confidence", "")),
            "data_completeness": dict(metrics.get("data_completeness", {})) if isinstance(metrics.get("data_completeness"), dict) else {},
            "raw": dict(sr),
        }

    @staticmethod
    def _missing(uid: str, status: str, *, segment: str = "") -> ProductAdviceUpstreamBundle:
        return {
            "data_status": status,
            "segment": segment,
            "segment_name": "",
            "overall_risk": "",
            "overall_value": "",
            "behavior_tags": {},
            "financial_tags": {},
            "confidence": "",
            "data_completeness": {},
            "raw": {},
        }
```

**Verify green**：`python -m pytest tests/test_product_advice_phase1.py -v -k DataAccess` → **4 passed**

**Commit**：`feat(skills): product_advice data_access from comprehensive`

---

### Task B.3 — feature_builder（normalize）

**Files**
- Modify：`app/runtime_skills/product_advice/feature_builder.py`
- Test：扩展 `tests/test_product_advice_phase1.py`

**TDD step 1**：写测试

```python
# tests/test_product_advice_phase1.py（追加）
from app.runtime_skills.product_advice.feature_builder import ProductAdviceFeatureBuilder


class ProductAdviceFeatureBuilderTests(unittest.TestCase):
    def test_build_normalizes(self):
        ctx = build_product_advice_run_context("U1")
        upstream = ProductAdviceUpstreamProvider().fetch("U1", ctx, comprehensive_result=_comp_result(segment="s2 "))
        # data_access 已 normalize，但 feature_builder 兜底
        fb = ProductAdviceFeatureBuilder().build(upstream, ctx)
        self.assertEqual(fb["segment"], "S2")
        self.assertEqual(fb["multi_head_risk"], "中")
        self.assertEqual(fb["contact_channel"], "WhatsApp")
```

**Verify red** → 1 failed

**TDD step 2**：实现

```python
# app/runtime_skills/product_advice/feature_builder.py
"""Feature builder layer for the Product Advice pipeline."""

from __future__ import annotations

from app.runtime_skills.product_advice.contracts import (
    ProductAdviceFeatureBundle,
    ProductAdviceRunContext,
    ProductAdviceUpstreamBundle,
)


class ProductAdviceFeatureBuilder:
    def build(
        self,
        upstream: ProductAdviceUpstreamBundle,
        context: ProductAdviceRunContext,
    ) -> ProductAdviceFeatureBundle:
        bt = upstream.get("behavior_tags", {}) or {}
        ft = upstream.get("financial_tags", {}) or {}
        return {
            "segment": str(upstream.get("segment", "")).strip().upper(),
            "overall_risk": str(upstream.get("overall_risk", "")),
            "overall_value": str(upstream.get("overall_value", "")),
            "multi_head_risk": str(ft.get("multi_head_risk", "")),
            "debt_pressure": str(ft.get("debt_pressure", "")),
            "borrowing_urgency": str(ft.get("borrowing_urgency", "")),
            "product_activity": str(bt.get("product_activity", "")),
            "contact_channel": str(bt.get("best_contact_channel", "")),
            "contact_time": str(bt.get("best_contact_time", "")),
        }
```

**Verify green** → 1 passed

**Commit**：`feat(skills): product_advice feature_builder`

---

### Task B.4 — decision_engine（查表）

**Files**
- Modify：`app/runtime_skills/product_advice/decision_engine.py`
- Test：扩展 `tests/test_product_advice_phase1.py`

**TDD step 1**：写测试

```python
class ProductAdviceDecisionEngineTests(unittest.TestCase):
    def test_decide_s2(self):
        fb = {"segment": "S2", "overall_risk": "中低", "overall_value": "中高",
              "multi_head_risk": "中", "debt_pressure": "中", "borrowing_urgency": "高",
              "product_activity": "高", "contact_channel": "WhatsApp", "contact_time": "晚间19-21点"}
        ctx = build_product_advice_run_context("U1")
        decision = ProductAdviceDecisionEngine().decide(fb, ctx)
        self.assertEqual(decision["segment"], "S2")
        self.assertEqual(decision["renewal_strategy"]["action"], "续贷优惠")
        self.assertEqual(decision["recommended_channel"]["best_time"], "晚间19-21点")

    def test_decide_s5_no_renewal(self):
        fb = {"segment": "S5", "overall_risk": "高", "overall_value": "中",
              "multi_head_risk": "高", "debt_pressure": "高", "borrowing_urgency": "高",
              "product_activity": "中", "contact_channel": "SMS", "contact_time": "工作日"}
        decision = ProductAdviceDecisionEngine().decide(fb, build_product_advice_run_context("U1"))
        self.assertIn("不主动", decision["renewal_strategy"]["action"])
        self.assertIsNone(decision["credit_line_action"]["delta_pct_range"])

    def test_build_prompt_payload(self):
        fb = {"segment": "S1", "overall_risk": "低", "overall_value": "高",
              "multi_head_risk": "低", "debt_pressure": "低", "borrowing_urgency": "低",
              "product_activity": "高", "contact_channel": "WhatsApp", "contact_time": ""}
        eng = ProductAdviceDecisionEngine()
        decision = eng.decide(fb, build_product_advice_run_context("U1"))
        payload = eng.build_prompt_payload(fb, decision)
        self.assertEqual(payload["segment"], "S1")
        self.assertIn("renewal_strategy", payload)
```

**Verify red** → 3 failed

**TDD step 2**：实现

```python
# app/runtime_skills/product_advice/decision_engine.py
"""Decision engine layer for the Product Advice pipeline."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.country_packs.mx.product_advice_rules import MX_PRODUCT_ADVICE_RULES
from app.country_packs.mx.segments import MX_SEGMENT_NAMES
from app.runtime_skills.product_advice.contracts import (
    ProductAdviceDecisionResult,
    ProductAdviceFeatureBundle,
    ProductAdviceRunContext,
)


class ProductAdviceDecisionEngine:
    def decide(
        self,
        feature_bundle: ProductAdviceFeatureBundle,
        context: ProductAdviceRunContext,
    ) -> ProductAdviceDecisionResult:
        seg = feature_bundle["segment"]
        rule = deepcopy(MX_PRODUCT_ADVICE_RULES.get(seg, {}))
        channel = deepcopy(rule.get("recommended_channel", {})) or {"primary": "", "secondary": None}
        channel["best_time"] = feature_bundle.get("contact_time", "")
        contact_channel_override = feature_bundle.get("contact_channel", "")
        if contact_channel_override and seg not in ("S5",):
            channel["primary"] = contact_channel_override

        rng = rule.get("credit_line_action", {}).get("delta_pct_range")
        credit_line = deepcopy(rule.get("credit_line_action", {}))
        if isinstance(rng, tuple):
            credit_line["delta_pct_range"] = list(rng)

        return {
            "segment": seg,
            "renewal_strategy": deepcopy(rule.get("renewal_strategy", {})),
            "credit_line_action": credit_line,
            "rate_plan": deepcopy(rule.get("rate_plan", {})),
            "recommended_channel": channel,
            "priority": str(rule.get("priority", "")),
            "tags": [str(t) for t in rule.get("tags", [])],
        }

    def build_prompt_payload(
        self,
        feature_bundle: ProductAdviceFeatureBundle,
        decision_result: ProductAdviceDecisionResult,
    ) -> dict[str, Any]:
        seg = feature_bundle["segment"]
        return {
            "segment": seg,
            "segment_name": MX_SEGMENT_NAMES.get(seg, ""),
            "feature_bundle": dict(feature_bundle),
            "renewal_strategy": decision_result.get("renewal_strategy", {}),
            "credit_line_action": decision_result.get("credit_line_action", {}),
            "rate_plan": decision_result.get("rate_plan", {}),
            "recommended_channel": decision_result.get("recommended_channel", {}),
            "priority": decision_result.get("priority", ""),
        }
```

**Verify green** → 3 passed

**Commit**：`feat(skills): product_advice decision_engine S1-S6 lookup`

---

### Task B.5 — explainer（mock 降级 + LLM 增强）

**Files**
- Modify：`app/runtime_skills/product_advice/explainer.py`
- Create：`app/prompts/product_advice_prompt.md`
- Test：扩展 `tests/test_product_advice_phase1.py`

**TDD step 1**：写测试（仅 mock 模式行为，不打 real LLM）

```python
class ProductAdviceExplainerTests(unittest.TestCase):
    def test_mock_mode_skips_llm(self):
        from pathlib import Path
        client = ModelClient()
        client.mode = "mock"
        client.model_name = "test-model"
        prompt_path = Path("app/prompts/product_advice_prompt.md")
        explainer = ProductAdviceExplainer(client, prompt_path)
        ctx = build_product_advice_run_context("U1")
        result = explainer.explain("U1", {"segment": "S2"}, {"segment": "S2"}, {"segment": "S2"}, ctx)
        self.assertEqual(result["status"], "model_mode_mock")
        self.assertFalse(result["used_llm"])
        self.assertEqual(result["payload"], {})
```

**TDD step 2**：写 Prompt 模板

```markdown
<!-- app/prompts/product_advice_prompt.md -->
# Role
你是墨西哥消费金融市场的产品策略顾问，为已分群（S1-S6）的用户生成可执行的产品建议话术。

# Task
基于 Skill 4 综合画像输出和 Skill 5 规则引擎已确定的策略字段（renewal_strategy / credit_line_action / rate_plan / recommended_channel），生成自然语言说明与 3-5 条具体话术（talking_points）。

# Input
- uid: {{uid}}
- payload: {{payload}}

# Rules
1. 不要编造具体金额、利率数字（金额由 structured_result 中的字段决定，本字段只做说明）。
2. talking_points 必须可直接发送给客户，每条 ≤ 60 字。
3. 输出 JSON：{"recommendation_summary": str, "talking_points": [str, ...], "risk_warnings": [str, ...]}
```

**TDD step 3**：实现 explainer（mock 路径直接返回 skipped 结构，real LLM 路径调用 ModelClient.generate_structured）

```python
# app/runtime_skills/product_advice/explainer.py
"""Explainer layer for the Product Advice pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.logger import get_logger
from app.core.model_client import ModelClient
from app.runtime_skills.product_advice.contracts import (
    ProductAdviceDecisionResult,
    ProductAdviceExplanationResult,
    ProductAdviceFeatureBundle,
    ProductAdviceRunContext,
)


logger = get_logger(__name__)


class ProductAdviceExplainer:
    def __init__(self, model_client: ModelClient, prompt_path: Path) -> None:
        self.model_client = model_client
        self.prompt_path = Path(prompt_path)

    def explain(
        self,
        uid: str,
        feature_bundle: ProductAdviceFeatureBundle,
        decision_result: ProductAdviceDecisionResult,
        prompt_payload: dict[str, Any],
        context: ProductAdviceRunContext,
    ) -> ProductAdviceExplanationResult:
        if self.model_client.mode == "mock":
            return self._skipped("model_mode_mock")

        prompt = self._build_prompt(uid, prompt_payload)
        fallback = {"recommendation_summary": "", "talking_points": [], "risk_warnings": []}
        result = self.model_client.generate_structured(
            skill_name="product_advice",
            prompt=prompt,
            fallback_result=fallback,
            response_schema={
                "type": "object",
                "properties": {
                    "recommendation_summary": {"type": "string"},
                    "talking_points": {"type": "array", "items": {"type": "string"}},
                    "risk_warnings": {"type": "array", "items": {"type": "string"}},
                },
            },
        )
        payload = result.get("structured_result", {}) if isinstance(result.get("structured_result"), dict) else {}
        accepted = result.get("status") == "ok" and bool(str(payload.get("recommendation_summary", "")).strip())
        status = "ok" if accepted else "model_unavailable"
        return {
            "status": status,
            "payload": payload if accepted else {},
            "fallback_reason": "" if accepted else str(result.get("status", "model_unavailable")),
            "used_llm": accepted,
            "model_name": str(result.get("model_name", self.model_client.model_name) or ""),
        }

    def _skipped(self, reason: str) -> ProductAdviceExplanationResult:
        return {
            "status": reason,
            "payload": {},
            "fallback_reason": reason,
            "used_llm": False,
            "model_name": self.model_client.model_name,
        }

    def _build_prompt(self, uid: str, prompt_payload: dict[str, Any]) -> str:
        template = self.prompt_path.read_text(encoding="utf-8") if self.prompt_path.exists() \
            else "uid={{uid}} payload={{payload}}"
        return template.replace("{{uid}}", uid).replace(
            "{{payload}}", json.dumps(prompt_payload, ensure_ascii=False, separators=(",", ":")),
        )
```

**Verify green** → 1 passed

**Commit**：`feat(skills): product_advice explainer (mock + real LLM paths)`

---

### Task B.6 — assembler + 入口接线 + 全管线集成测试

**Files**
- Modify：`app/runtime_skills/product_advice/assembler.py`
- Modify：`app/runtime_skills/product_advice_agent.py`（重写为薄入口）
- Test：扩展 `tests/test_product_advice_phase1.py`（端到端 + missing 路径）

**TDD step 1**：写集成测试

```python
class ProductAdviceSkillTests(unittest.TestCase):
    def setUp(self):
        from app.runtime_skills.product_advice_agent import ProductAdviceSkill
        client = ModelClient()
        client.mode = "mock"
        self.skill = ProductAdviceSkill(client)

    def test_e2e_s2(self):
        out = self.skill.analyze("U1", comprehensive_profile_result=_comp_result(segment="S2"))
        self.assertIn("structured_result", out)
        sr = out["structured_result"]
        self.assertEqual(sr["status"], "ok")
        self.assertEqual(sr["segment"], "S2")
        self.assertEqual(sr["renewal_strategy"]["action"], "续贷优惠")
        self.assertIn("S2", sr["tags"])
        self.assertEqual(out["charts"], [])
        self.assertTrue(out["report_markdown"].startswith("## "))
        # AgentOutput schema 校验
        from app.schemas.final_response import AgentOutput
        AgentOutput.model_validate(out)

    def test_e2e_each_segment(self):
        for seg in ("S1", "S2", "S3", "S4", "S5", "S6"):
            out = self.skill.analyze("U1", comprehensive_profile_result=_comp_result(segment=seg))
            self.assertEqual(out["structured_result"]["segment"], seg)
            self.assertEqual(out["structured_result"]["status"], "ok")

    def test_missing_upstream(self):
        out = self.skill.analyze("U1", comprehensive_profile_result={})
        self.assertEqual(out["structured_result"]["status"], "data_missing")
        self.assertIn("数据不足", out["summary"])

    def test_invalid_segment(self):
        out = self.skill.analyze("U1", comprehensive_profile_result=_comp_result(segment="X9"))
        self.assertEqual(out["structured_result"]["status"], "data_missing")

    def test_model_trace_mock(self):
        out = self.skill.analyze("U1", comprehensive_profile_result=_comp_result())
        mt = out["structured_result"]["model_trace"]
        self.assertEqual(mt["mode"], "mock")
        self.assertFalse(mt["used_llm"])
        self.assertEqual(mt["fallback_reason"], "model_mode_mock")
```

**TDD step 2**：实现 assembler

```python
# app/runtime_skills/product_advice/assembler.py
"""Assembler layer for the Product Advice pipeline."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.core.model_client import ModelClient
from app.country_packs.mx.segments import MX_SEGMENT_NAMES
from app.runtime_skills.product_advice.contracts import (
    ProductAdviceDecisionResult,
    ProductAdviceExplanationResult,
    ProductAdviceFeatureBundle,
    ProductAdvicePageResult,
    ProductAdviceRunContext,
    ProductAdviceUpstreamBundle,
)
from app.schemas.product_advice import ProductAdviceStructuredResult
from app.utils.pydantic_compat import model_dump_compat, model_validate_compat


class ProductAdvicePageAssembler:
    def __init__(self, model_client: ModelClient) -> None:
        self.model_client = model_client

    def build_missing_output(
        self,
        uid: str,
        context: ProductAdviceRunContext,
        upstream: ProductAdviceUpstreamBundle,
    ) -> ProductAdvicePageResult:
        reason = upstream.get("data_status", "missing")
        structured = ProductAdviceStructuredResult(
            uid=uid, status="data_missing", segment="", segment_name="",
            tags=["数据不足", "建议人工复核"],
            model_trace={
                "mode": self.model_client.mode, "used_llm": False,
                "model_name": self.model_client.model_name,
                "fallback_reason": f"upstream_{reason}",
            },
        )
        return {
            "summary": "上游 comprehensive_profile 数据不足，建议人工复核后再生成产品策略。",
            "structured_result": model_dump_compat(structured),
            "charts": [],
            "report_markdown": f"## {uid} · 产品策略建议\n\n> 数据不足（{reason}），建议人工复核。",
        }

    def build_fallback_structured(
        self,
        uid: str,
        feature_bundle: ProductAdviceFeatureBundle,
        decision_result: ProductAdviceDecisionResult,
    ) -> dict[str, Any]:
        seg = decision_result["segment"]
        structured = ProductAdviceStructuredResult(
            uid=uid, status="ok",
            segment=seg, segment_name=MX_SEGMENT_NAMES.get(seg, ""),
            renewal_strategy=decision_result.get("renewal_strategy", {}),
            credit_line_action=decision_result.get("credit_line_action", {}),
            rate_plan=decision_result.get("rate_plan", {}),
            recommended_channel=decision_result.get("recommended_channel", {}),
            priority=decision_result.get("priority", ""),
            tags=list(decision_result.get("tags", [])),
            model_trace={
                "mode": self.model_client.mode, "used_llm": False,
                "model_name": self.model_client.model_name, "fallback_reason": "",
            },
        )
        return model_dump_compat(structured)

    def assemble(
        self,
        uid: str,
        fallback_structured: dict[str, Any],
        explanation_result: ProductAdviceExplanationResult,
    ) -> ProductAdvicePageResult:
        structured = deepcopy(fallback_structured)
        payload = explanation_result.get("payload", {})
        if explanation_result.get("used_llm") and isinstance(payload, dict):
            structured["explanation"] = payload

        structured["model_trace"] = {
            "mode": self.model_client.mode,
            "used_llm": bool(explanation_result.get("used_llm")),
            "model_name": str(explanation_result.get("model_name", self.model_client.model_name) or ""),
            "fallback_reason": str(explanation_result.get("fallback_reason", "")),
        }
        validated = model_dump_compat(model_validate_compat(ProductAdviceStructuredResult, structured))
        summary = self._build_summary(validated, payload)
        report = self._build_report(uid, validated, payload)
        return {
            "summary": summary,
            "structured_result": validated,
            "charts": [],
            "report_markdown": report,
        }

    @staticmethod
    def _build_summary(structured: dict[str, Any], explanation: dict[str, Any]) -> str:
        if isinstance(explanation, dict) and explanation.get("recommendation_summary"):
            return str(explanation["recommendation_summary"])
        seg = structured.get("segment", "")
        seg_name = structured.get("segment_name", "")
        ren = structured.get("renewal_strategy", {}).get("action", "")
        line = structured.get("credit_line_action", {}).get("action", "")
        ch = structured.get("recommended_channel", {}).get("primary", "")
        return f"{seg} {seg_name}建议{ren} + {line}，{ch} 触达。"

    @staticmethod
    def _build_report(uid: str, structured: dict[str, Any], explanation: dict[str, Any]) -> str:
        seg = structured.get("segment", "")
        seg_name = structured.get("segment_name", "")
        rs = structured.get("renewal_strategy", {})
        cla = structured.get("credit_line_action", {})
        rp = structured.get("rate_plan", {})
        ch = structured.get("recommended_channel", {})
        lines = [
            f"## {uid} · {seg} {seg_name} · 产品策略建议",
            "",
            f"- **续贷策略**：{rs.get('action', '')}（{rs.get('reason', '')}）",
            f"- **额度动作**：{cla.get('action', '')}（{cla.get('reason', '')}）",
            f"- **利率方案**：{rp.get('plan', '')}" + (f"（锚定 {rp['anchor_competitor']}）" if rp.get("anchor_competitor") else ""),
            f"- **触达渠道**：{ch.get('primary', '')}（{ch.get('best_time', '')}）",
            f"- **优先级**：{structured.get('priority', '')}",
        ]
        if isinstance(explanation, dict) and explanation.get("talking_points"):
            lines.append("")
            lines.append("### 话术建议")
            for tp in explanation.get("talking_points", []):
                lines.append(f"- {tp}")
        return "\n".join(lines)
```

**TDD step 3**：重写入口

```python
# app/runtime_skills/product_advice_agent.py
"""ProductAdviceSkill — six-step pipeline orchestrator (thin entry)."""
from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.model_client import ModelClient
from app.runtime_skills.base import BaseSkill
from app.runtime_skills.product_advice import (
    ProductAdviceDecisionEngine,
    ProductAdviceExplainer,
    ProductAdviceFeatureBuilder,
    ProductAdvicePageAssembler,
    ProductAdviceUpstreamProvider,
    build_product_advice_run_context,
)


class ProductAdviceSkill(BaseSkill):
    name = "product_advice"
    stage = 2
    depends_on: list[str] = ["comprehensive_profile"]

    def __init__(self, model_client: ModelClient) -> None:
        self.model_client = model_client
        prompt_path = settings.resolve_path(f"{settings.prompt_dir}/product_advice_prompt.md")
        self.upstream_provider = ProductAdviceUpstreamProvider()
        self.feature_builder = ProductAdviceFeatureBuilder()
        self.decision_engine = ProductAdviceDecisionEngine()
        self.explainer = ProductAdviceExplainer(model_client, prompt_path)
        self.assembler = ProductAdvicePageAssembler(model_client)

    def analyze(self, uid: str, **kwargs: Any) -> dict[str, Any]:
        context = build_product_advice_run_context(uid)
        upstream = self.upstream_provider.fetch(
            uid, context,
            comprehensive_result=kwargs.get("comprehensive_profile_result", {}) or {},
        )
        if upstream["data_status"] != "ok":
            return self.assembler.build_missing_output(uid, context, upstream)

        feature_bundle = self.feature_builder.build(upstream, context)
        decision_result = self.decision_engine.decide(feature_bundle, context)
        prompt_payload = self.decision_engine.build_prompt_payload(feature_bundle, decision_result)
        fallback_structured = self.assembler.build_fallback_structured(uid, feature_bundle, decision_result)
        explanation_result = self.explainer.explain(
            uid, feature_bundle, decision_result, prompt_payload, context,
        )
        return self.assembler.assemble(uid, fallback_structured, explanation_result)
```

**Verify green**：
```bash
python -m pytest tests/test_product_advice_phase1.py tests/test_product_advice_rules.py -v
```
预期：所有 ProductAdvice 相关测试 passed（约 13 用例）。

**Commit**：`feat(skills): product_advice assembler + thin entry + e2e tests`

---

## 6. Phase C — OpsAdvice 六步管线（TDD）

> 与 Phase B 同构，每个 Task 的代码块基本一一对应。**为节省篇幅，本节不重复粘贴完整代码**，但每个 Task 给出与 ProductAdvice 的差异点 + 验证命令 + commit message。所有 schema、规则键、字段名按 Design Doc §8 与 Plan §4 Task A.2 已经确定。

| Task | 与 B 的差异 | Verify 命令 | Commit |
|---|---|---|---|
| C.1 contracts run_context | 同 B.1，类名替换为 `OpsAdviceRunContext` / `build_ops_advice_run_context` | `python -c "from app.runtime_skills.ops_advice import build_ops_advice_run_context"` | `feat(skills): ops_advice run-context builder` |
| C.2 data_access | 同 B.2 但抽出的字段子集是 `churn_risk / debt_pressure / multi_head_risk / contact_*`，仍统一用 `MX_SEGMENTS` 校验 | `pytest tests/test_ops_advice_phase1.py -v -k DataAccess` | `feat(skills): ops_advice data_access from comprehensive` |
| C.3 feature_builder | 输出 `OpsAdviceFeatureBundle`，多 `churn_risk` 字段，少 `borrowing_urgency / product_activity` | `pytest tests/test_ops_advice_phase1.py -v -k FeatureBuilder` | `feat(skills): ops_advice feature_builder` |
| C.4 decision_engine | 查 `MX_OPS_ADVICE_RULES`；**额外**：churn_risk == "高" 时 churn_warning.level 上调一档（无→轻→中→强，已强不变；不动 collection_strategy） | `pytest tests/test_ops_advice_phase1.py -v -k DecisionEngine` | `feat(skills): ops_advice decision_engine + churn escalation` |
| C.5 explainer + prompt | Prompt 模板 `app/prompts/ops_advice_prompt.md`：输出 `outreach_script`（WhatsApp / SMS 草稿）+ `retention_pitch`；mock 路径同 B.5 | `pytest tests/test_ops_advice_phase1.py -v -k Explainer` | `feat(skills): ops_advice explainer (mock + real LLM paths)` |
| C.6 assembler + 入口 + e2e | `OpsAdviceStructuredResult` 替换；`_build_summary` 模板：`f"{seg} {seg_name}：{collection.intensity} 催收 + {churn.level}流失预警，{ch} 触达。"` | `pytest tests/test_ops_advice_phase1.py tests/test_ops_advice_rules.py -v` | `feat(skills): ops_advice assembler + thin entry + e2e tests` |

### C.4 churn 升级规则代码片段（关键差异，必须写明）

```python
# decision_engine.py 末尾增加
_LEVEL_ORDER = ["无", "轻", "中", "强"]

def _escalate_churn(level: str) -> str:
    if level not in _LEVEL_ORDER:
        return level
    idx = _LEVEL_ORDER.index(level)
    return _LEVEL_ORDER[min(idx + 1, len(_LEVEL_ORDER) - 1)]

# decide() 内部，从 rule 取 churn_warning 后：
if str(feature_bundle.get("churn_risk", "")) == "高":
    churn_warning["level"] = _escalate_churn(str(churn_warning.get("level", "无")))
    if "竞品APP安装" not in churn_warning.get("signals", []):
        churn_warning.setdefault("signals", []).append("行为侧 churn_risk=高")
```

### C.4 churn 升级测试（关键差异）

```python
def test_decide_s2_with_high_churn_escalates(self):
    fb = {"segment": "S2", "churn_risk": "高", "debt_pressure": "中",
          "multi_head_risk": "中", "contact_channel": "WhatsApp",
          "contact_time": "晚间", "overall_risk": "中低"}
    decision = OpsAdviceDecisionEngine().decide(fb, build_ops_advice_run_context("U1"))
    self.assertEqual(decision["churn_warning"]["level"], "轻")  # 无 → 轻

def test_decide_s5_strong_already_caps(self):
    fb = {"segment": "S5", "churn_risk": "高", "debt_pressure": "高",
          "multi_head_risk": "高", "contact_channel": "SMS",
          "contact_time": "工作日", "overall_risk": "高"}
    decision = OpsAdviceDecisionEngine().decide(fb, build_ops_advice_run_context("U1"))
    self.assertEqual(decision["churn_warning"]["level"], "强")  # 强不再上调
```

---

## 7. Phase D — 编排接线 + 集成

### Task D.1 — orchestrator 已注册（确认 + 无操作）

baseline 已完成：[orchestrator.py:55-56](../../app/services/orchestrator.py#L55-L56) 已 register；[orchestrator.py:88-96](../../app/services/orchestrator.py#L88-L96) 已回填。

**Verify**：
```bash
python -c "from app.services.orchestrator import AnalysisOrchestrator; o=AnalysisOrchestrator(); print(o.registry.list_all())"
```
预期：包含 `'product_advice'`, `'ops_advice'`。

**No commit**（baseline 已 commit）。

---

### Task D.2 — 端到端集成测试

**Files**
- Test：`tests/test_orchestrator_stage2_phase1.py`（新建）

```python
"""Stage-2 advisory skills end-to-end via the orchestrator."""
from __future__ import annotations

import unittest

from app.repositories.local_repository import LocalUserRepository
from app.services.orchestrator import AnalysisOrchestrator


SAMPLE_UID = "824812551379353600"


class OrchestratorStage2Tests(unittest.TestCase):
    def test_user_analysis_result_has_advisory_fields(self):
        # 仅在样本数据存在时跑；若 repo 没数据，跳过
        repo = LocalUserRepository()
        try:
            data = repo.get_app_data(SAMPLE_UID)
        except Exception:
            self.skipTest("Sample uid data not available locally")
        if not data:
            self.skipTest("Sample uid data empty")

        orch = AnalysisOrchestrator()
        resp = orch.analyze([SAMPLE_UID])
        self.assertEqual(len(resp.results), 1)
        ur = resp.results[0]
        self.assertIsNotNone(ur.product_advice)
        self.assertIsNotNone(ur.ops_advice)
        # 形状检查
        self.assertIn(ur.product_advice.structured_result.get("status"), ("ok", "data_missing"))
        self.assertIn(ur.ops_advice.structured_result.get("status"), ("ok", "data_missing"))
```

**Verify**：`python -m pytest tests/test_orchestrator_stage2_phase1.py -v` → 1 passed（或 skipped）

**Commit**：`test(skills): orchestrator stage-2 advisory integration`

---

## 8. Phase E — 收尾

### Task E.1 — TASK.md 打勾 + [complete] 标注

**Files**
- Modify：`TASK.md`：把 P2 两条 stub 项改写为已完成（带本期 commit 范围）

**Verify**：`python -m pytest tests/ data_acquisition_agent/tests/ -q` → **预期 ≥ 304 passed**（278 + 26 新增 ≈ 304，详见汇总表）

**Commit**：`feat(skills): operation skills (product + ops advice) [complete]`

---

## 9. 停止条件

满足以下全部条件视为完成：

1. ✅ Phase A–E 全部 commit
2. ✅ 全量 pytest 0 failed（warnings 只剩既有 PydanticDeprecatedSince20）
3. ✅ `AnalysisOrchestrator` 跑端到端时 `UserAnalysisResult.product_advice / .ops_advice` 非 None
4. ✅ Mock 模式下，所有 6 个 segment 输出 deterministic（同一输入 → 同一 `structured_result`）
5. ✅ 上游 `status != "ok"` 或 segment 不在 S1–S6 时，输出 `status="data_missing"`，不抛异常
6. ✅ TASK.md / PLANNING.md 同步
7. ✅ 不 push（等用户统一推送）

## 10. 测试用例数汇总表

| 文件 | Task | 用例数 |
|---|---|---|
| `tests/test_product_advice_rules.py` | A.1 | 4 |
| `tests/test_ops_advice_rules.py` | A.2 | 4 |
| `tests/test_product_advice_phase1.py` | B.2 / B.3 / B.4 / B.5 / B.6 | 4 + 1 + 3 + 1 + 5 = **14** |
| `tests/test_ops_advice_phase1.py` | C.2 / C.3 / C.4 / C.5 / C.6 | 4 + 1 + 4 + 1 + 5 = **15** |
| `tests/test_orchestrator_stage2_phase1.py` | D.2 | 1 |
| **新增小计** |  | **38** |
| 既有全量回归基线 | — | 278 (passed) + 1 (skipped) |
| **预计最终** |  | **316 passed, 1 skipped** |

## 11. Commit 策略

- **Baseline 已打**：`7d7483c [baseline] operation-skills: design doc + stage=2 skeleton`
- **每个 Task 一个 commit**（顺序见 §4–§7 各小节末尾的 commit 行）
- **最后一个 commit 标 `[complete]`**：`feat(skills): operation skills (product + ops advice) [complete]`
- **不 push**：所有 commit 留在本地，等用户统一推送
- 共计预估 commits：A 段 2 + B 段 6 + C 段 6 + D 段 1 + E 段 1 = **16 个 commit**（含 [complete]）

## 12. 五点检查法自检

1. **Spec 合规性**：✅ 所有规则字段都来自 Design Doc §7 / §8 表格；segment 枚举来自 §八；上游字段来自 §六 6.2 JSON。Schema 字段命名与 Design Doc §4 / §7 / §8 一致。
2. **代码质量**：✅ 六步管线对齐 app_profile 风格；薄入口 ≤ 80 行；country_pack 抽离；deepcopy 防止 rule mutation；Pydantic v2 通过 `pydantic_compat`。
3. **测试完整性**：✅ 正常路径（6 segment 各一）+ 边界（status≠ok / segment≠S1-S6 / 空 dict）+ 降级（mock 模式）+ schema 校验（AgentOutput.model_validate）+ 集成（orchestrator）。
4. **可逆性**：✅ 全部新增文件 + 已有 stub 替换；UserAnalysisResult 字段为 Optional + None 默认；既有测试 0 修改 → 改动可回滚到 baseline。
5. **可观测性**：✅ `model_trace` 三态（mock / used_llm=true / model_unavailable）显式透传；`structured_result.status` 区分 ok / data_missing；fallback_reason 携带原因字符串。

## 13. 执行检查清单（实际执行时勾选）

- [ ] A.1 product_advice_rules + 4 tests passed
- [ ] A.2 ops_advice_rules + 4 tests passed
- [ ] B.1 contracts run_context
- [ ] B.2 data_access + 4 tests passed
- [ ] B.3 feature_builder + 1 test passed
- [ ] B.4 decision_engine + 3 tests passed
- [ ] B.5 explainer + prompt + 1 test passed
- [ ] B.6 assembler + entry + 5 tests passed
- [ ] C.1 contracts run_context
- [ ] C.2 data_access + 4 tests passed
- [ ] C.3 feature_builder + 1 test passed
- [ ] C.4 decision_engine + churn escalation + 4 tests passed
- [ ] C.5 explainer + prompt + 1 test passed
- [ ] C.6 assembler + entry + 5 tests passed
- [ ] D.2 orchestrator integration + 1 test passed
- [ ] E.1 TASK.md / PLANNING.md / [complete] commit
- [ ] 全量 pytest ≥ 316 passed, 0 failed
