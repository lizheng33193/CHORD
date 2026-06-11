# Behavior / Credit Schema 补全 Plan

> 状态：Draft（等待用户回复"确认执行"后进入实现）
> 关联 TASK：`P1: 补全 Behavior/Credit Pydantic Schema`
> 关联 Design Doc：[docs/specs/standardized-labels-design.md](../specs/standardized-labels-design.md)
> 决策来源：用户已确认 Q1=B / Q2=C / Q3=A
> 分支：main，基线 commit：`6fad5cb`（标准化标签 commit）

---

## 0. 决策摘要

| 维度 | 选择 | 实施方向 |
| --- | --- | --- |
| Q1 字段范围 | B | 强类型子模型 + 顶层 level 字段，对齐 app_profile 风格 |
| Q2 metrics 兼容 | C | 完全保留 metrics 不动；Plan 标注 DEPRECATED；本轮不清理 |
| Q3 label_builder 迁移 | A | 新路径优先 → 旧路径 fallback；不引入双源告警 |

**强类型边界**（不在本期范围）：
- 不强类型化 `evidence` / `metrics` 内部所有原始数值字段
- 不动 `comprehensive_profile` / `app_profile` schema
- 不动 6 个 Skill 的 decision_engine / explainer / contracts.py / agent 入口

---

## 1. 范围与文件清单

### 1.1 修改文件
- `app/schemas/behavior_profile.py` — 新增 4 个子模型 + 顶层字段
- `app/schemas/credit_profile.py` — 新增 4 个子模型 + 顶层字段
- `app/runtime_skills/behavior_profile/assembler.py` — 回填顶层字段
- `app/runtime_skills/credit_profile/assembler.py` — 回填顶层字段
- `app/services/label_builder.py` — 新路径优先 + 旧路径 fallback
- `tests/test_standardized_labels.py` — 新增 fallback / 新路径覆盖

### 1.2 新增文件
- `tests/test_behavior_credit_schema.py` — 子模型构造单测 + assembler 回填单测（behavior 1 条 + credit 1 条）

### 1.3 不修改文件（约束）
- `app/runtime_skills/behavior_profile/decision_engine.py` / `explainer.py` / `contracts.py` / `data_access.py` / `feature_builder.py`
- `app/runtime_skills/credit_profile/decision_engine.py` / `explainer.py` / `contracts.py` / `data_access.py` / `feature_builder.py`
- `app/runtime_skills/behavior_profile_agent.py` / `credit_profile_agent.py`
- `app/runtime_skills/comprehensive*` / `app_profile*` / `product_advice*` / `ops_advice*`
- `data_acquisition_agent/` 任何文件
- 其它 schema 文件（`app_profile.py` / `comprehensive_profile.py` / `product_advice.py` / `ops_advice.py` / `final_response.py`）
- `TASK.md` / `PLANNING.md` / `CLAUDE.md`

---

## 2. Phase A — Schema 强类型模型设计

### 2.1 字段映射依据

来源：`behavior_profile/decision_engine.py:194-210` / `credit_profile/decision_engine.py:97-112` 已在 `BehaviorDecisionResult` / `CreditDecisionResult` 中产出对应 dict 块。本 Plan 只是把这些已有 dict **再产出一份强类型副本**到 Pydantic schema，metrics 原样保留。

### 2.2 Behavior 子模型 → 字段路径

| Pydantic 子模型 | 来源 dict（DecisionResult key） | 字段（保留来源 key 名） |
| --- | --- | --- |
| `RepaymentWillingness` | `repayment_willingness` | level / display_level / repayment_event_count / reasoning |
| `ProductSensitivity` | `product_sensitivity` | level / display_level / purchase_preference / pricing_event_count / reasoning |
| `ChurnRisk` | `churn_risk` | level / display_level / warning_event_count / dropoff_stage / journey_risk_count / reasoning |
| `ContactPreference` | `contact_preference` | best_channel / best_time / confidence / reason / observed_channels |

**顶层 level 直取字段**（与子模型并存，方便 label_builder 优先读取）：
- `repayment_willingness_level: str = "unknown"`
- `product_sensitivity_level: str = "unknown"`
- `churn_risk_level: str = "unknown"`

`engagement_level` 已在顶层（保持不变）。

### 2.3 Credit 子模型 → 字段路径

| Pydantic 子模型 | 来源 dict（DecisionResult key） | 字段（保留来源 key 名） |
| --- | --- | --- |
| `FinancialMaturity` | `financial_maturity` | level / display_level / credit_history_years / has_bank_credit_card / reasoning |
| `DebtPressure` | `debt_pressure` | level / display_level / total_debt_mxn / monthly_payment_mxn / avg_credit_utilization / reasoning |
| `CreditStability` | `credit_stability` | level / display_level / grade / total_delinquencies / max_dpd / months_since_last_delinquency / reasoning |
| `BorrowingUrgency` | `borrowing_urgency` | level / display_level / inquiries_3m / inquiries_6m / inquiry_sources_type / reasoning |

**顶层 level 直取字段**：
- `financial_maturity_level: str = "unknown"`
- `debt_pressure_level: str = "unknown"`
- `credit_stability_level: str = "unknown"`
- `borrowing_urgency_level: str = "unknown"`
- `risk_level: str = "unknown"`（来自 `metrics.risk_level`，这是 Skill 整体 risk 的对外口径）

### 2.4 metrics 字段处理（DEPRECATED 标注）

**保留** `metrics: dict[str, Any]` 原样不动。
在 schema 字段定义处加一行注释：
```python
# DEPRECATED: Prefer top-level typed fields and sub-models.
# Kept for backward compatibility; planned removal in a future schema cleanup.
metrics: dict[str, Any] = Field(default_factory=dict)
```

不在本轮做任何 metrics 清理。

---

## Phase A — Tasks

### A1: 新增 Behavior 4 个子模型 + 顶层 level 字段

**文件**：`app/schemas/behavior_profile.py`（当前 22 行）

**默认值规则**：
- **业务枚举字段**（`level` / `purchase_preference` / `dropoff_stage` 等表示业务等级或类别的离散枚举）→ 默认 `"unknown"`，与 standardized-labels Design Doc 的 unknown 不变量一致，避免"未填即低风险"误判。
- **展示字段**（`display_level` / `reasoning` / `reason` / `best_channel` / `best_time` 等用于 UI / 报告渲染的人类可读文本）→ 默认空字符串 `""`。理由：调用方逻辑不会以它们为判定输入;用 `"unknown"` 反而会被前端原样渲染出来污染界面,空字符串更适合 conditional render。
- **数值 / 布尔 / 列表**：与 `decision_engine` 输出口径一致,分别默认 `0` / `0.0` / `False` / `[]`。

**完整改写后内容**：
```python
"""Schema definitions for behavior profile outputs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RepaymentWillingness(BaseModel):
    """Repayment willingness sub-profile."""

    level: str = "unknown"
    display_level: str = ""
    repayment_event_count: int = 0
    reasoning: str = ""


class ProductSensitivity(BaseModel):
    """Product sensitivity (a.k.a. credit-line willingness proxy) sub-profile."""

    level: str = "unknown"
    display_level: str = ""
    purchase_preference: str = "unknown"
    pricing_event_count: int = 0
    reasoning: str = ""


class ChurnRisk(BaseModel):
    """Churn risk sub-profile."""

    level: str = "unknown"
    display_level: str = ""
    warning_event_count: int = 0
    dropoff_stage: str = "unknown"
    journey_risk_count: int = 0
    reasoning: str = ""


class ContactPreference(BaseModel):
    """Best contact channel and timing sub-profile."""

    best_channel: str = ""
    best_time: str = ""
    confidence: str = "low"
    reason: str = ""
    observed_channels: list[str] = Field(default_factory=list)


class BehaviorProfileStructuredResult(BaseModel):
    """Structured output generated by behavior profile skill."""

    agent_name: str = "behavior_profile_agent"
    uid: str
    status: str = "ok"
    engagement_level: str = "unknown"

    # Top-level level fields (preferred by label_builder; mirror sub-model.level).
    repayment_willingness_level: str = "unknown"
    product_sensitivity_level: str = "unknown"
    churn_risk_level: str = "unknown"

    # Strong-typed sub-models (Q1=B).
    repayment_willingness: RepaymentWillingness = Field(default_factory=RepaymentWillingness)
    product_sensitivity: ProductSensitivity = Field(default_factory=ProductSensitivity)
    churn_risk: ChurnRisk = Field(default_factory=ChurnRisk)
    contact_preference: ContactPreference = Field(default_factory=ContactPreference)

    evidence: dict[str, Any] = Field(default_factory=dict)

    # DEPRECATED: Prefer top-level typed fields and sub-models above.
    # Kept for backward compatibility; planned removal in a future schema cleanup.
    metrics: dict[str, Any] = Field(default_factory=dict)

    tags: list[str] = Field(default_factory=list)
    model_trace: dict[str, Any] = Field(default_factory=dict)
```

**验证命令**：
```bash
python -c "from app.schemas.behavior_profile import BehaviorProfileStructuredResult, RepaymentWillingness, ProductSensitivity, ChurnRisk, ContactPreference; r = BehaviorProfileStructuredResult(uid='u1'); print(r.model_dump())"
python -m pytest tests/test_behavior_profile_phase18.py -q
```

**预期结果**：
- 第一行 import 通过，打印的 dict 含全部新字段（默认值 unknown / 0 / ""）
- 既有 behavior 测试 0 failed（旧字段未改动，新字段全为可选默认值）

**回滚点**：`git checkout HEAD -- app/schemas/behavior_profile.py`

---

### A2: 新增 Credit 4 个子模型 + 顶层 level 字段

**文件**：`app/schemas/credit_profile.py`（当前 20 行）

**默认值规则**：
- **业务枚举字段**（`level` / `inquiry_sources_type` 等离散枚举）→ 默认 `"unknown"`，对齐 standardized-labels Design Doc 的 unknown 不变量。
- **展示字段**（`display_level` / `reasoning` / `grade` / `avg_credit_utilization` 等供 UI / 报告渲染的人类可读文本）→ 默认空字符串 `""`。理由同 A1：避免占位文本 `"unknown"` 污染前端界面，调用方逻辑不会以它们为判定输入。
- **数值 / 布尔**：与 `decision_engine` 输出口径一致，分别默认 `0` / `0.0` / `False`。

**完整改写后内容**：
```python
"""Schema definitions for credit profile outputs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FinancialMaturity(BaseModel):
    """Financial maturity sub-profile."""

    level: str = "unknown"
    display_level: str = ""
    credit_history_years: float = 0.0
    has_bank_credit_card: bool = False
    reasoning: str = ""


class DebtPressure(BaseModel):
    """Debt pressure sub-profile."""

    level: str = "unknown"
    display_level: str = ""
    total_debt_mxn: int = 0
    monthly_payment_mxn: int = 0
    avg_credit_utilization: str = ""
    reasoning: str = ""


class CreditStability(BaseModel):
    """Credit stability sub-profile."""

    level: str = "unknown"
    display_level: str = ""
    grade: str = ""
    total_delinquencies: int = 0
    max_dpd: int = 0
    months_since_last_delinquency: int = 0
    reasoning: str = ""


class BorrowingUrgency(BaseModel):
    """Borrowing urgency (a.k.a. borrow-hunger proxy) sub-profile."""

    level: str = "unknown"
    display_level: str = ""
    inquiries_3m: int = 0
    inquiries_6m: int = 0
    inquiry_sources_type: str = "unknown"
    reasoning: str = ""


class CreditProfileStructuredResult(BaseModel):
    """Structured output generated by credit profile skill."""

    agent_name: str = "credit_profile_agent"
    uid: str
    status: str = "ok"

    # Top-level level fields (preferred by label_builder).
    risk_level: str = "unknown"
    financial_maturity_level: str = "unknown"
    debt_pressure_level: str = "unknown"
    credit_stability_level: str = "unknown"
    borrowing_urgency_level: str = "unknown"

    # Strong-typed sub-models (Q1=B).
    financial_maturity: FinancialMaturity = Field(default_factory=FinancialMaturity)
    debt_pressure: DebtPressure = Field(default_factory=DebtPressure)
    credit_stability: CreditStability = Field(default_factory=CreditStability)
    borrowing_urgency: BorrowingUrgency = Field(default_factory=BorrowingUrgency)

    evidence: dict[str, Any] = Field(default_factory=dict)

    # DEPRECATED: Prefer top-level typed fields and sub-models above.
    # Kept for backward compatibility; planned removal in a future schema cleanup.
    metrics: dict[str, Any] = Field(default_factory=dict)

    tags: list[str] = Field(default_factory=list)
    model_trace: dict[str, Any] = Field(default_factory=dict)
```

**验证命令**：
```bash
python -c "from app.schemas.credit_profile import CreditProfileStructuredResult, FinancialMaturity, DebtPressure, CreditStability, BorrowingUrgency; r = CreditProfileStructuredResult(uid='u1'); print(r.model_dump())"
python -m pytest tests/test_credit_profile_phase17.py -q
```

**预期结果**：
- import 通过，打印 dict 含全部新字段
- 既有 credit 测试 0 failed

**回滚点**：`git checkout HEAD -- app/schemas/credit_profile.py`

---

## Phase B — Assembler 回填顶层字段

### 设计要点
- **不改 decision_engine**：所有数据已经在 `decision_result` 里，assembler 只做"再写一份到顶层"
- **不改 metrics 写法**：metrics 仍由 `build_fallback_structured` 完整写入
- **`build_missing_output` 不变**：data_missing 走默认值即可（顶层 level 默认 "unknown"，子模型默认 unknown）
- 由于 assembler 现在用 dict 路径写入，新增字段直接通过 Pydantic 校验进入

### B1: Behavior assembler 回填顶层字段 + 子模型

**文件**：`app/runtime_skills/behavior_profile/assembler.py`

**修改位置**：`build_fallback_structured` 方法（当前在 [behavior_profile/assembler.py:89-111](../../app/runtime_skills/behavior_profile/assembler.py)）

**改动方式**：扩充 `BehaviorProfileStructuredResult(...)` 的构造参数。

**完整改写后的方法体**：
```python
def build_fallback_structured(
    self,
    uid: str,
    _raw_data: BehaviorRawData,
    _feature_bundle: BehaviorFeatureBundle,
    decision_result: BehaviorDecisionResult,
) -> dict[str, object]:
    metrics = decision_result.get("metrics", {})
    structured = BehaviorProfileStructuredResult(
        uid=uid,
        status="ok",
        engagement_level=str(
            decision_result.get("engagement_profile", {}).get("level", "light")
            or "light"
        ),
        # Top-level level fields (mirror metrics; preferred by label_builder).
        repayment_willingness_level=str(
            metrics.get("repayment_willingness_level", "unknown") or "unknown"
        ),
        product_sensitivity_level=str(
            metrics.get("product_sensitivity_level", "unknown") or "unknown"
        ),
        churn_risk_level=str(
            metrics.get("churn_risk_level", "unknown") or "unknown"
        ),
        # Strong-typed sub-models — pass dicts; Pydantic coerces to model.
        repayment_willingness=decision_result.get("repayment_willingness", {}) or {},
        product_sensitivity=decision_result.get("product_sensitivity", {}) or {},
        churn_risk=decision_result.get("churn_risk", {}) or {},
        contact_preference=decision_result.get("contact_preference", {}) or {},
        evidence=decision_result.get("evidence_seed", {}),
        metrics=metrics,  # DEPRECATED but retained.
        tags=[
            str(tag)
            for tag in decision_result.get("tags_rule", [])
            if str(tag).strip()
        ],
    )
    return model_dump_compat(structured)
```

**验证命令**：
```bash
python -m pytest tests/test_behavior_profile_phase18.py -q
```

**预期结果**：既有 behavior 测试 0 failed（顶层字段从 metrics 同源复制；子模型构造从已有 decision dict 直接传入，Pydantic 接受 dict）。

**回滚点**：`git checkout HEAD -- app/runtime_skills/behavior_profile/assembler.py`

---

### B2: Credit assembler 回填顶层字段 + 子模型

**文件**：`app/runtime_skills/credit_profile/assembler.py`

**修改位置**：`build_fallback_structured` 方法（当前在 [credit_profile/assembler.py:78-92](../../app/runtime_skills/credit_profile/assembler.py)）

**完整改写后的方法体**：
```python
def build_fallback_structured(
    self,
    uid: str,
    _raw_data: CreditRawData,
    _feature_bundle: CreditFeatureBundle,
    decision_result: CreditDecisionResult,
) -> dict[str, object]:
    metrics = decision_result.get("metrics", {})
    structured = CreditProfileStructuredResult(
        uid=uid,
        status="ok",
        # Top-level level fields.
        risk_level=str(metrics.get("risk_level", "unknown") or "unknown"),
        financial_maturity_level=str(
            metrics.get("financial_maturity_level", "unknown") or "unknown"
        ),
        debt_pressure_level=str(
            metrics.get("debt_pressure_level", "unknown") or "unknown"
        ),
        credit_stability_level=str(
            metrics.get("credit_stability_level", "unknown") or "unknown"
        ),
        borrowing_urgency_level=str(
            metrics.get("borrowing_urgency_level", "unknown") or "unknown"
        ),
        # Strong-typed sub-models.
        financial_maturity=decision_result.get("financial_maturity", {}) or {},
        debt_pressure=decision_result.get("debt_pressure", {}) or {},
        credit_stability=decision_result.get("credit_stability", {}) or {},
        borrowing_urgency=decision_result.get("borrowing_urgency", {}) or {},
        evidence=decision_result.get("evidence_seed", {}),
        metrics=metrics,  # DEPRECATED but retained.
        tags=[str(tag) for tag in decision_result.get("tags_rule", []) if str(tag).strip()],
    )
    return model_dump_compat(structured)
```

**验证命令**：
```bash
python -m pytest tests/test_credit_profile_phase17.py -q
```

**预期结果**：既有 credit 测试 0 failed。

**回滚点**：`git checkout HEAD -- app/runtime_skills/credit_profile/assembler.py`

---

## Phase C — label_builder 路径升级

### C1: 新路径优先 + 旧路径 fallback

**文件**：`app/services/label_builder.py`

**改动方式**：在 `risk_labels` / `behavior_labels` 三处用 `_first_non_empty(新路径, 旧路径)` 包裹。**`borrow_hunger` 已存在 fallback，扩展为三层**。

**完整 diff（仅展示改动的 risk_labels 与 behavior_labels 块）**：

```python
"risk_labels": {
    "multi_loan_risk": _get_path(app_sr, ["risk_assessment", "level"]),
    "credit_stability": _first_non_empty(
        _get_path(cre_sr, ["credit_stability", "level"]),         # NEW: top sub-model
        _get_path(cre_sr, ["credit_stability_level"]),            # NEW: top-level level
        _get_path(cre_sr, ["metrics", "credit_stability_level"]), # OLD: metrics
    ),
    "debt_pressure": _first_non_empty(
        _get_path(cre_sr, ["debt_pressure", "level"]),
        _get_path(cre_sr, ["debt_pressure_level"]),
        _get_path(cre_sr, ["metrics", "debt_pressure_level"]),
    ),
    "borrow_hunger": _first_non_empty(
        _get_path(cre_sr, ["borrowing_urgency", "level"]),
        _get_path(cre_sr, ["borrowing_urgency_level"]),
        _get_path(cre_sr, ["metrics", "borrowing_urgency_level"]),
        _get_path(cre_sr, ["metrics", "borrowing_hunger_level"]),  # legacy fallback
    ),
},
"behavior_labels": {
    "repayment_willingness": _first_non_empty(
        _get_path(beh_sr, ["repayment_willingness", "level"]),
        _get_path(beh_sr, ["repayment_willingness_level"]),
        _get_path(beh_sr, ["metrics", "repayment_willingness_level"]),
    ),
    "credit_line_willingness": _first_non_empty(
        _get_path(beh_sr, ["product_sensitivity", "level"]),
        _get_path(beh_sr, ["product_sensitivity_level"]),
        _get_path(beh_sr, ["metrics", "product_sensitivity_level"]),
    ),
    "churn_risk": _first_non_empty(
        _get_path(beh_sr, ["churn_risk", "level"]),
        _get_path(beh_sr, ["churn_risk_level"]),
        _get_path(beh_sr, ["metrics", "churn_risk_level"]),
        _get_path(ops_sr, ["churn_warning", "level"]),
    ),
    "outreach_preference": _first_non_empty(
        _get_path(ops_sr, ["outreach_channel", "primary"]),
        _get_path(prod_sr, ["recommended_channel", "primary"]),
        _get_path(beh_sr, ["contact_preference", "best_channel"]),    # NEW: top sub-model
        _get_path(beh_sr, ["evidence", "contact_preference", "best_channel"]),  # OLD
    ),
},
```

**banking_level / financial_maturity_level 的特别说明**：
- 当前 `banking_level` 来源是 `app_profile.financial_maturity.level`（与 credit 的 financial_maturity 同名但语义不同），保持不变。
- 不引入 credit `financial_maturity_level` 作 banking_level 的来源（语义不同，避免污染）。

**验证命令**：
```bash
python -m pytest tests/test_standardized_labels.py -q
```

**预期结果**：既有 13 个用例全绿（旧 metrics 路径 fallback 仍工作）。

**回滚点**：`git checkout HEAD -- app/services/label_builder.py`

---

## Phase D — Tests 补全

### D1: 新增 schema 单测 — `tests/test_behavior_credit_schema.py`

**文件**：`tests/test_behavior_credit_schema.py`（新建）

**完整内容**：
```python
"""Unit tests for Behavior/Credit schema sub-models and top-level level fields."""

from __future__ import annotations

import pytest

from app.schemas.behavior_profile import (
    BehaviorProfileStructuredResult,
    ChurnRisk,
    ContactPreference,
    ProductSensitivity,
    RepaymentWillingness,
)
from app.schemas.credit_profile import (
    BorrowingUrgency,
    CreditProfileStructuredResult,
    CreditStability,
    DebtPressure,
    FinancialMaturity,
)


# -----------------------------
# A. Default construction (backward compat)
# -----------------------------


def test_behavior_default_construction_has_all_new_fields():
    r = BehaviorProfileStructuredResult(uid="u1")
    assert r.repayment_willingness_level == "unknown"
    assert r.product_sensitivity_level == "unknown"
    assert r.churn_risk_level == "unknown"
    assert isinstance(r.repayment_willingness, RepaymentWillingness)
    assert isinstance(r.product_sensitivity, ProductSensitivity)
    assert isinstance(r.churn_risk, ChurnRisk)
    assert isinstance(r.contact_preference, ContactPreference)
    assert r.metrics == {}  # DEPRECATED but retained


def test_credit_default_construction_has_all_new_fields():
    r = CreditProfileStructuredResult(uid="u1")
    assert r.risk_level == "unknown"
    assert r.financial_maturity_level == "unknown"
    assert r.debt_pressure_level == "unknown"
    assert r.credit_stability_level == "unknown"
    assert r.borrowing_urgency_level == "unknown"
    assert isinstance(r.financial_maturity, FinancialMaturity)
    assert isinstance(r.debt_pressure, DebtPressure)
    assert isinstance(r.credit_stability, CreditStability)
    assert isinstance(r.borrowing_urgency, BorrowingUrgency)
    assert r.metrics == {}


# -----------------------------
# B. Sub-model construction from dict (mirrors assembler usage)
# -----------------------------


def test_behavior_submodel_from_dict():
    r = BehaviorProfileStructuredResult(
        uid="u1",
        repayment_willingness={
            "level": "high",
            "display_level": "高",
            "repayment_event_count": 3,
            "reasoning": "rule x",
        },
    )
    assert r.repayment_willingness.level == "high"
    assert r.repayment_willingness.repayment_event_count == 3


def test_credit_submodel_from_dict():
    r = CreditProfileStructuredResult(
        uid="u1",
        debt_pressure={
            "level": "medium",
            "total_debt_mxn": 12345,
            "monthly_payment_mxn": 678,
        },
    )
    assert r.debt_pressure.level == "medium"
    assert r.debt_pressure.total_debt_mxn == 12345


# -----------------------------
# C. Top-level + metrics co-existence
# -----------------------------


def test_behavior_top_level_and_metrics_independent():
    """Top-level level field is independent of metrics value (assembler fills both)."""
    r = BehaviorProfileStructuredResult(
        uid="u1",
        repayment_willingness_level="high",
        metrics={"repayment_willingness_level": "high", "extra_metric": 42},
    )
    assert r.repayment_willingness_level == "high"
    assert r.metrics["repayment_willingness_level"] == "high"
    assert r.metrics["extra_metric"] == 42


# -----------------------------
# D. Assembler backfill (1 behavior + 1 credit)
# -----------------------------


def test_behavior_assembler_backfills_top_level_and_submodels():
    """B1 assembler should mirror metrics levels into top-level fields and
    construct sub-models from decision_result dict blocks."""
    from app.runtime_skills.behavior_profile.assembler import BehaviorPageAssembler

    decision_result = {
        "engagement_profile": {"level": "balanced"},
        "repayment_willingness": {"level": "high", "repayment_event_count": 2},
        "product_sensitivity": {"level": "medium", "pricing_event_count": 1},
        "churn_risk": {"level": "low"},
        "contact_preference": {"best_channel": "WhatsApp", "best_time": "evening"},
        "evidence_seed": {"contact_preference": {"best_channel": "WhatsApp"}},
        "metrics": {
            "repayment_willingness_level": "high",
            "product_sensitivity_level": "medium",
            "churn_risk_level": "low",
        },
        "tags_rule": ["t1"],
    }
    out = BehaviorPageAssembler().build_fallback_structured(
        uid="u1",
        _raw_data={},
        _feature_bundle={},
        decision_result=decision_result,
    )
    assert out["repayment_willingness_level"] == "high"
    assert out["product_sensitivity_level"] == "medium"
    assert out["churn_risk_level"] == "low"
    assert out["repayment_willingness"]["level"] == "high"
    assert out["contact_preference"]["best_channel"] == "WhatsApp"
    # metrics retained intact (DEPRECATED but compatible).
    assert out["metrics"]["repayment_willingness_level"] == "high"


def test_credit_assembler_backfills_top_level_and_submodels():
    """B2 assembler should mirror metrics levels into top-level fields and
    construct sub-models from decision_result dict blocks."""
    from app.runtime_skills.credit_profile.assembler import CreditPageAssembler

    decision_result = {
        "financial_maturity": {"level": "medium", "credit_history_years": 3.0},
        "debt_pressure": {"level": "medium", "total_debt_mxn": 12345},
        "credit_stability": {"level": "medium_high", "grade": "B"},
        "borrowing_urgency": {"level": "high", "inquiries_3m": 4},
        "evidence_seed": {},
        "metrics": {
            "risk_level": "medium",
            "financial_maturity_level": "medium",
            "debt_pressure_level": "medium",
            "credit_stability_level": "medium_high",
            "borrowing_urgency_level": "high",
        },
        "tags_rule": [],
    }
    out = CreditPageAssembler().build_fallback_structured(
        uid="u1",
        _raw_data={},
        _feature_bundle={},
        decision_result=decision_result,
    )
    assert out["risk_level"] == "medium"
    assert out["credit_stability_level"] == "medium_high"
    assert out["borrowing_urgency_level"] == "high"
    assert out["credit_stability"]["level"] == "medium_high"
    assert out["debt_pressure"]["total_debt_mxn"] == 12345
    assert out["metrics"]["credit_stability_level"] == "medium_high"
```

**验证命令**：
```bash
python -m pytest tests/test_behavior_credit_schema.py -q
```

**预期结果**：7 tests passed（5 子模型 / 顶层 + 2 assembler 回填）。

**回滚点**：`rm tests/test_behavior_credit_schema.py`

---

### D2: 扩充 `tests/test_standardized_labels.py` — 新路径优先 + 旧路径 fallback

**文件**：`tests/test_standardized_labels.py`

**改动方式**：在文件末尾追加一个新分组 `# G. New schema path priority`。

**完整追加内容**：
```python
# -----------------------------
# G. New schema paths take precedence over legacy metrics path
# -----------------------------


def test_G1_new_path_wins_over_metrics_for_credit():
    """When credit.credit_stability.level (new) and metrics.credit_stability_level (old)
    both exist, new path wins."""
    credit = _agent_output(
        {
            "status": "ok",
            "credit_stability": {"level": "high"},  # new path
            "credit_stability_level": "medium",     # top-level mirror
            "metrics": {"credit_stability_level": "low"},  # legacy
        }
    )
    labels = build_standardized_labels(
        app_profile=_full_app_ok(),
        behavior_profile=_full_behavior_ok(),
        credit_profile=credit,
        comprehensive_profile=_full_comprehensive_ok(),
        product_advice=_full_product_advice(),
        ops_advice=_full_ops_advice(),
    )
    assert labels["risk_labels"]["credit_stability"] == "high"


def test_G2_top_level_mirror_wins_when_submodel_missing():
    credit = _agent_output(
        {
            "status": "ok",
            "credit_stability_level": "medium_high",
            "metrics": {"credit_stability_level": "low"},
        }
    )
    labels = build_standardized_labels(
        app_profile=_full_app_ok(),
        behavior_profile=_full_behavior_ok(),
        credit_profile=credit,
        comprehensive_profile=_full_comprehensive_ok(),
        product_advice=_full_product_advice(),
        ops_advice=_full_ops_advice(),
    )
    assert labels["risk_labels"]["credit_stability"] == "medium_high"


def test_G3_legacy_metrics_path_still_works_when_new_paths_absent():
    credit = _agent_output(
        {
            "status": "ok",
            "metrics": {"credit_stability_level": "low"},  # only legacy
        }
    )
    labels = build_standardized_labels(
        app_profile=_full_app_ok(),
        behavior_profile=_full_behavior_ok(),
        credit_profile=credit,
        comprehensive_profile=_full_comprehensive_ok(),
        product_advice=_full_product_advice(),
        ops_advice=_full_ops_advice(),
    )
    assert labels["risk_labels"]["credit_stability"] == "low"


def test_G4_behavior_repayment_three_path_priority():
    behavior = _agent_output(
        {
            "status": "ok",
            "engagement_level": "balanced",
            "repayment_willingness": {"level": "high"},
            "repayment_willingness_level": "medium_high",
            "metrics": {
                "repayment_willingness_level": "low",
                "product_sensitivity_level": "medium",
                "churn_risk_level": "low",
            },
            "evidence": {"contact_preference": {"best_channel": "WhatsApp"}},
        }
    )
    labels = build_standardized_labels(
        app_profile=_full_app_ok(),
        behavior_profile=behavior,
        credit_profile=_full_credit_ok(),
        comprehensive_profile=_full_comprehensive_ok(),
        product_advice=_full_product_advice(),
        ops_advice=_full_ops_advice(),
    )
    assert labels["behavior_labels"]["repayment_willingness"] == "high"


def test_G5_outreach_falls_through_to_top_level_contact_preference():
    """ops/product 都缺时，behavior 顶层 contact_preference 命中（新路径优先于 evidence）。"""
    behavior = _agent_output(
        {
            "status": "ok",
            "engagement_level": "balanced",
            "metrics": {
                "repayment_willingness_level": "medium",
                "product_sensitivity_level": "medium",
                "churn_risk_level": "low",
            },
            "contact_preference": {"best_channel": "Push"},  # new top
            "evidence": {"contact_preference": {"best_channel": "SMS"}},  # legacy
        }
    )
    ops_no_channel = _agent_output(
        {"status": "ok", "segment": "S2", "churn_warning": {"level": "low"}}
    )
    product_no_channel = _agent_output({"status": "ok", "segment": "S2"})
    labels = build_standardized_labels(
        app_profile=_full_app_ok(),
        behavior_profile=behavior,
        credit_profile=_full_credit_ok(),
        comprehensive_profile=_full_comprehensive_ok(),
        product_advice=product_no_channel,
        ops_advice=ops_no_channel,
    )
    assert labels["behavior_labels"]["outreach_preference"] == "Push"
```

**验证命令**：
```bash
python -m pytest tests/test_standardized_labels.py -q
```

**预期结果**：原 13 + 新 5 = 18 tests passed。

**回滚点**：`git checkout HEAD -- tests/test_standardized_labels.py`

---

## Phase E — 端到端验证

### E1: 全量回归

**命令**：
```bash
python -m pytest tests/ data_acquisition_agent/tests/ -q --tb=short
```

**预期结果（相对基线）**：
- 基线：在 A/B/C/D 任何代码改动前，先跑一次 `python -m pytest tests/ data_acquisition_agent/tests/ -q` 记下 `passed_baseline` / `skipped_baseline` / `failed_baseline = 0`。
- 本期完成后，**新增 passed = D1 新增用例数（7）+ D2 新增用例数（5）= 12**；`failed` 必须仍为 0；`skipped` 不变。
- 验收公式：`passed_after == passed_baseline + 12` 且 `failed_after == 0` 且 `skipped_after == skipped_baseline`。
- 不写死绝对数字（基线会随其它无关 commit 漂移）。

**关键测试文件全绿条件（强制项，验收必查）**：
即使全量回归整体相对基线增量正确，仍须单独确认下列两个文件 100% 通过、0 failed / 0 error：
```bash
python -m pytest tests/test_behavior_credit_schema.py tests/test_standardized_labels.py -v
```
- `tests/test_behavior_credit_schema.py` — 必须 7 passed（D1 全部用例）
- `tests/test_standardized_labels.py` — 必须 18 passed（既有 13 + D2 新增 5）
- 任一文件出现 failed / error → 视为本期未达验收，禁止 commit / push，立即停下定位。

如果出现失败：
- 立刻定位失败用例，不修复 schema 字段以外的代码
- 失败如果是既有 behavior/credit 测试断言新字段不存在 → 该测试需要更新（但本 Plan 假设既有测试只断言旧字段，应该不受影响）
- 出现意外失败，先停下汇报，不擅自扩大改动范围

### E2: orchestrator 实跑（mock 模式）

不调 real LLM、不读真实数据，只验证 schema/orchestrator 不在管线中报错：

**命令**：
```bash
python -c "
from app.services.label_builder import build_standardized_labels
from app.schemas.behavior_profile import BehaviorProfileStructuredResult
from app.schemas.credit_profile import CreditProfileStructuredResult

# Construct two structured_results with new shape; ensure label_builder picks new paths.
beh = BehaviorProfileStructuredResult(
    uid='u1', status='ok',
    repayment_willingness_level='high',
    repayment_willingness={'level': 'high'},
).model_dump()
cre = CreditProfileStructuredResult(
    uid='u1', status='ok',
    credit_stability_level='medium_high',
    credit_stability={'level': 'medium_high'},
).model_dump()
labels = build_standardized_labels(
    app_profile={'structured_result': {'status':'ok','financial_maturity':{'level':'medium'},'risk_assessment':{'level':'low'},'consumption_profile':{'level':'high'}}},
    behavior_profile={'structured_result': beh},
    credit_profile={'structured_result': cre},
    comprehensive_profile={'structured_result': {'status':'ok','persona':'p','metrics':{'segment':'S2','confidence_level':'high'}}},
    product_advice=None, ops_advice=None,
)
import json; print(json.dumps(labels, ensure_ascii=False, indent=2))
"
```

**预期结果**：
- `risk_labels.credit_stability` = `"medium_high"`
- `behavior_labels.repayment_willingness` = `"high"`
- 17 key 形状完整

---

## 3. 推荐执行顺序与耗时

| 顺序 | Task | 预计耗时 | 依赖 |
| --- | --- | --- | --- |
| 1 | A1 — Behavior schema 子模型 | 4 min | — |
| 2 | A2 — Credit schema 子模型 | 4 min | — |
| 3 | D1 — schema 单测（先红后绿） | 5 min | A1 / A2 |
| 4 | B1 — Behavior assembler 回填 | 4 min | A1 |
| 5 | B2 — Credit assembler 回填 | 4 min | A2 |
| 6 | 中间回归：behavior + credit phase18/17 | 2 min | B1 / B2 |
| 7 | C1 — label_builder 三层路径 | 5 min | B1 / B2 |
| 8 | D2 — label_builder 扩展测试 | 5 min | C1 |
| 9 | E1 — 全量回归 | ~3.5 min（既有 329 用例耗时 ~200s） | 全部前置 |
| 10 | E2 — orchestrator 烟雾验证 | 1 min | E1 |
| 11 | Commit（单 commit）+ push 确认 | 2 min | 用户审核通过 |

**总预计**：~40 min（含 1 次全量回归耗时）。

**Commit 计划**（仅 1 个 commit，符合 Phase 3 风格）：
```
feat(schemas): typed sub-models for behavior/credit + label_builder path upgrade

- Add 4+4 strong-typed sub-models (RepaymentWillingness/ChurnRisk/...)
- Mirror level fields at structured_result top-level (preferred path)
- Keep metrics intact (DEPRECATED, slated for future cleanup)
- Assemblers backfill new fields without touching decision_engine
- label_builder uses new-path-first → metrics-fallback (Q3=A)
```

**Push 计划**：在用户明确说"push"后才 push 到 `github` remote（不推 origin），符合 CLAUDE.md。

---

## 4. 风险清单

### 4.1 兼容性风险

| ID | 风险 | 影响 | 缓解 |
| --- | --- | --- | --- |
| RC1 | 既有消费方读 `metrics.repayment_willingness_level` 仍工作？ | 高 — 若打破，前端 / 报告 / 既有测试爆炸 | metrics 完全不动（Q2=C），新增字段都是 Optional 默认值，理论零回归 |
| RC2 | Pydantic v2 dict→model 强制校验，传入异常类型会抛 ValidationError | 中 — assembler 传 dict 时若字段 type 不匹配（如 expected int 但拿到 str）会抛 | 子模型字段全部默认值，`decision_engine` 已经在产出对应类型；A1/A2 字段类型与 decision_engine 输出对齐 |
| RC3 | `model_dump_compat` 序列化后嵌套子模型变 dict，前端读法不变 | 低 | 既有 assembler 已用此 helper，子模型行为与 ModelTrace 等子模型一致 |
| RC4 | 既有 behavior/credit 测试断言 `metrics` 形状 | 中 | metrics 不动，断言不受影响；但若有断言 "no extra fields"（如 `==` 比较整个 structured_result），会因新字段失败 — E1 前需要先看 phase18/17 测试断言风格 |

### 4.2 测试覆盖风险

| ID | 风险 | 影响 | 缓解 |
| --- | --- | --- | --- |
| RT1 | label_builder 新增 4 个路径，G 系列 5 用例可能不足 | 中 | G1-G5 覆盖了"新路径胜出 / top-level mirror 胜出 / legacy fallback / 三层切换"4 个核心场景；如评审认为不够，再加用例 |
| RT2 | 子模型构造没覆盖"传入非法字典"边界 | 低 | Pydantic 会抛 ValidationError；assembler 传入的都是 decision_engine 产出的合法字典；非法路径在 E1 全量回归时若爆出再补 |
| RT3 | 没做端到端 mock orchestrator 测试 | 中 | E2 烟雾验证 + 既有 `test_orchestrator_stage2_phase1.py` 可覆盖；如不够，Plan 之外再补 |

### 4.3 回归风险

| ID | 风险 | 影响 | 缓解 |
| --- | --- | --- | --- |
| RR1 | A1/A2 改 schema 后 chart_builder 读取 structured_result 时字段变化 | 中 — chart_builder 在 [scripts/chart_builder.py](../../app/scripts/chart_builder.py) 由 assembler 调用 | 不改 metrics/evidence；chart_builder 应不依赖新字段；E1 全量回归覆盖 |
| RR2 | report_renderer 渲染新字段时格式异常 | 低 — render_agent_report 接收整个 structured dict | 新字段都是默认 unknown 字符串；不影响 markdown 模板 |
| RR3 | comprehensive_profile.decision_engine 读 `credit_structured.get("metrics", ...)` 等旧路径 | 低 — comprehensive 仍读 metrics，不读新路径 | metrics 不动 → comprehensive 行为不变；不在本 Plan 修改范围 |
| RR4 | data_missing 路径未回填新字段 → label_builder fallback 仍 OK 但顶层 level = unknown | 低 | 设计意图就是 unknown，符合 standardized_labels Design Doc 不变量 |

### 4.4 进度风险

| ID | 风险 | 影响 | 缓解 |
| --- | --- | --- | --- |
| RP1 | E1 全量回归 ~3.5 min，若失败排查耗时 | 中 | 每个 task 后先跑窄测试，缩小定位范围；Phase 完成后才跑全量 |
| RP2 | A1/A2 改 schema 触发 phase18/17 测试断言失败（断言整个 dict 形状） | 中 | 第 6 步"中间回归"提前发现；如失败先看断言风格再决定补 default fixture 还是改测试 |

---

## 5. 与既有 Plan / Doc 的关系

- 不破坏 [docs/specs/standardized-labels-design.md](../specs/standardized-labels-design.md) 任何不变量（17 key 形状、纯值结构、unknown 默认值）
- 不修改 standardized_labels 输出形状 — 只是 label_builder 内部抽取路径升级
- 与 TASK.md `P1: 补全 Behavior/Credit Pydantic Schema` 对齐
- 不进入 LangGraph 迁移（P3）

---

## 6. Non-goals（重申）

- ❌ 不补全 evidence / metrics 内部所有原始数值字段
- ❌ 不动 decision_engine / explainer / contracts.py
- ❌ 不动其它 4 个 Skill 的 schema
- ❌ 不动 final_response.py
- ❌ 不做 metrics 实质清理（DEPRECATED 仅是注释标注）
- ❌ 不引入运行时双源比对 / 告警逻辑
- ❌ 不调 real LLM
- ❌ 不读 data/ 真实数据
- ❌ 不修改 data_acquisition_agent/

---

## 7. 用户确认入口

请回复 **"确认执行"** 后我将按 §3 顺序进入实现，每个 phase 结束后停下汇报、等你确认下一 phase。
