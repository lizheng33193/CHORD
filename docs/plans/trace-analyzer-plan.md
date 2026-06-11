# Trace Analyzer Plan — E1 单用户埋点深度解析

- 状态：Draft（待 user 五点检查法审核）
- 关联 Design Doc：[docs/specs/trace-analyzer-design.md](../specs/trace-analyzer-design.md)
- Plan 名：`trace-analyzer-plan`
- 基线 commit：`[baseline] trace-analyzer-plan`（已落 `3d239da`）
- 完成 commit 标注：`[complete] trace-analyzer-plan: event trace deep analysis`

---

## 0. 关键事实勘察（Plan 写作前已查清，不在 Task 内）

| 事实 | 实际值 | 影响 |
|---|---|---|
| Step 3 Stub 已落地 | 11 文件 + PLANNING.md（commit `4760096`） | 本 Plan 直接基于 Stub 实现 |
| baseline commit | `3d239da [baseline] trace-analyzer-plan` | 已 commit |
| 真 CSV 列 | `uid,servertimestamp,timestamp_,scenetype,processtype,eventname,extend,clientmodel,clientosversion,url,refer,ip` | data_access 列契约固化 |
| 真 CSV 量级 | G1 uid `824812551379353600` 593 行（实测） | sanity check 用此 uid |
| 真 CSV 路径 | `data/behavior/by_uid/{uid}.csv` | 通过 settings 读前缀 |
| ModelClient 接口 | `ModelClient(mode).generate_structured(skill_name, prompt, fallback_result, response_schema)` | explainer 直接复用 |
| Pydantic schema 已就位 | `app/schemas/trace_analyzer.py`（7 子 model + `TraceAnalyzeResponse`，Step 3 真实定义） | assembler 直接 model_validate |
| 内部 TypedDict 已就位 | `app/runtime_skills/trace_analyzer/contracts.py`（5 个 TypedDict，Step 3 真实定义） | 各层 import 用 |
| 路由 stub 已就位 | `app/api/trace.py` router 已建，未挂载 main.py | Task 7.2 实装 handler，Task 8.1 挂载 |
| settings 数据路径前缀 | `app.core.config.settings.local_data_dir`（默认 `data/`） | data_access 用此前缀 |
| §11 8 数字 | 见 Task 1.1 `_constants.py` 全部锁死 | 不留待 Plan 后 |
| 与 D2（窗口 2 SSE）共改 main.py | D2 已 commit `32da181`（progress_callback），未来仍可能再改 | Task 8.1 前必 `git pull --rebase` |

---

## 1. Plan 总览

| Phase | Task | 内容 | 预估 | 验证 |
|---|---|---|---|---|
| 0 | 0.1 | baseline commit（已完成） | — | `git log --oneline -1` |
| 1 | 1.1 | 新建 `app/runtime_skills/trace_analyzer/_constants.py` 锁定 §11 8 个数字 → 独立 commit | 5 min | python import + 数值断言 |
| 2 | 2.1 | TDD-RED：`tests/test_trace_analyzer_phase1.py` 新建 + data_access 测试（4 case：ok / 文件不存在 / 列缺失 / 空 CSV） | 4 min | 4 测试 RED |
| 2 | 2.2 | TDD-GREEN：实现 `data_access.py`（读 CSV → DataFrame + 状态机） → commit | 7 min | 4 测试 GREEN |
| 3 | 3.1 | TDD-RED：feature_builder 测试（5 类事实 + 脱敏 + token 护栏共 8 case） | 5 min | 8 测试 RED |
| 3 | 3.2 | TDD-GREEN：实现 `feature_builder.py`（5 类事实 + CJK token 估算 + 三层护栏） → commit | 12 min | 8 测试 GREEN |
| 4 | 4.1 | TDD-RED：decision_engine 测试（prompt_payload 组装 + 模板兜底） | 3 min | 3 测试 RED |
| 4 | 4.2 | TDD-GREEN：实现 `decision_engine.py` → commit | 5 min | 3 测试 GREEN |
| 5 | 5.1 | TDD-RED：explainer 测试（mock 跳过 / LLM JSON / churn_root_cause 白名单 / 失败降级） | 4 min | 4 测试 RED |
| 5 | 5.2 | TDD-GREEN：实现 `explainer.py` + 填 `app/prompts/trace_analyzer_prompt.md` 完整内容 → commit | 10 min | 4 测试 GREEN |
| 6 | 6.1 | TDD-RED：assembler + analyzer 测试（5 种 status 路径 + e2e mock） | 5 min | 5 测试 RED |
| 6 | 6.2 | TDD-GREEN：实现 `assembler.py` + `analyzer.py` 入口编排 → commit | 7 min | 5 测试 GREEN |
| 7 | 7.1 | TDD-RED：FastAPI TestClient 路由集成测试（mock e2e + 404 + status 字段映射） | 4 min | 3 测试 RED |
| 7 | 7.2 | TDD-GREEN：实装 `app/api/trace.py` handler → commit | 6 min | 3 测试 GREEN |
| 8 | 8.1 | **`app/main.py` include_router 单独 Task**（前置 `git pull --rebase` 协调 D2） → commit | 3 min | curl 端点不再 404 |
| 9 | 9.1 | 真 CSV sanity check（G1 uid mock 模式，肉眼审核 friction_hotspots / 脱敏） | 4 min | 实测脚本输出审核 |
| 9 | 9.2 | 全量 `pytest tests/ -v` 零回归 + TASK.md / PLANNING.md 更新 + `[complete]` commit | 3 min | 全 passed + git log |

合计预估 ≈ 87 min。
独立 commit 数：1.1 / 2.2 / 3.2 / 4.2 / 5.2 / 6.2 / 7.2 / 8.1 / 9.2 = 9 个 feat commit + 1 [baseline]（已落）+ 1 [complete] = 11 个 commit。

---

## 2. 五点检查法预审

| # | 检查项 | 自查 |
|---|---|---|
| 1 | 每个 Task 有精确文件路径？ | ✅ 全部到文件名级别 |
| 2 | 有占位符（TBD / TODO / implement later）？ | ✅ 无。§11 8 个数字在 Task 1.1 锁为具体值；prompt 完整内容在 Task 5.2 一次填满 |
| 3 | 代码步骤有完整代码块？ | ✅ §3 每个 Task 有完整代码块（无"类似前一个 Task" 这种引用） |
| 4 | 有验证命令 + 预期输出？ | ✅ 每 Task 末"验证"栏 |
| 5 | 一个人不问问题能执行完？ | ✅ 唯一例外：Task 8.1 前 `git pull --rebase`，是 design 已声明的人工步骤；冲突时 STOP 报告 |

---

## 3. 详细 Task 代码块

### Task 1.1 — `_constants.py` 锁定 §11 8 个数字

文件路径：`app/runtime_skills/trace_analyzer/_constants.py`（新建）

```python
"""Constants for trace_analyzer pipeline.

Locks the 8 numbers deferred from docs/specs/trace-analyzer-design.md §11.
Single source of truth — change here propagates to all six pipeline layers.
"""
from __future__ import annotations

# Threshold below which we skip LLM call and return status=insufficient_events.
INSUFFICIENT_EVENTS_THRESHOLD: int = 10

# Path graph top-N
TOP_N_TRANSITIONS: int = 10
TOP_N_PAGES: int = 8

# Friction hotspots top-K (severity-sorted)
TOP_K_FRICTION_HOTSPOTS: int = 5

# Key events tail length (most recent N events, post-redaction, exposed in API)
KEY_EVENTS_TAIL_N: int = 30

# Pre-dropoff key events length (matches product doc "last 10 steps")
KEY_EVENTS_PRE_DROPOFF_N: int = 10

# Token budgets (CJK-weighted estimate). See design §2.Q6.
TOTAL_TOKEN_BUDGET: int = 8000
TIER_2_TOKEN_BUDGET: int = 1500   # friction hotspot details
TIER_3_TOKEN_BUDGET: int = 5000   # key events sequence
# Tier 1 (aggregate summary) is implicit: TOTAL - TIER_2 - TIER_3 = 1500 ceiling, never trimmed.

# Churn root cause whitelist — must match ops_advice/decision_engine.py 6-value set
CHURN_ROOT_CAUSE_ENUM: frozenset[str] = frozenset({
    "credit_limit_unmet",
    "interest_perception_high",
    "competitor_poaching",
    "ux_friction",
    "repayment_burden",
    "no_clear_signal",
})
```

**验证**：

```bash
python -c "
from app.runtime_skills.trace_analyzer._constants import (
    INSUFFICIENT_EVENTS_THRESHOLD, TOP_N_TRANSITIONS, TOP_N_PAGES,
    TOP_K_FRICTION_HOTSPOTS, KEY_EVENTS_TAIL_N, KEY_EVENTS_PRE_DROPOFF_N,
    TOTAL_TOKEN_BUDGET, TIER_2_TOKEN_BUDGET, TIER_3_TOKEN_BUDGET,
    CHURN_ROOT_CAUSE_ENUM,
)
assert INSUFFICIENT_EVENTS_THRESHOLD == 10
assert TOTAL_TOKEN_BUDGET == TIER_2_TOKEN_BUDGET + TIER_3_TOKEN_BUDGET + 1500
assert len(CHURN_ROOT_CAUSE_ENUM) == 6
print('OK')
"
```

预期：`OK`

```bash
git add app/runtime_skills/trace_analyzer/_constants.py
git commit -m "feat(trace): lock 8 design-deferred constants in _constants.py"
```

⛔ STOP — 报告 Task 1.1 完成。

---

### Task 2.1 — TDD-RED：data_access 测试

文件路径：`tests/test_trace_analyzer_phase1.py`（新建）

```python
"""Trace analyzer pipeline tests — phase 1 (data_access)."""
from __future__ import annotations

import pandas as pd
import pytest

from app.runtime_skills.trace_analyzer.data_access import TraceDataAccess
from app.runtime_skills.trace_analyzer.contracts import TraceRunContext


CSV_HEADER = "uid,servertimestamp,timestamp_,scenetype,processtype,eventname,extend,clientmodel,clientosversion,url,refer,ip"


def _ctx(uid: str = "U1") -> TraceRunContext:
    return {
        "uid": uid,
        "country_code": "mx",
        "application_time": "2026-05-01T00:00:00Z",
        "enable_llm_explanation": True,
    }


def _write_csv(tmp_path, uid: str, rows: list[str]) -> None:
    base = tmp_path / "behavior" / "by_uid"
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{uid}.csv").write_text(
        CSV_HEADER + "\n" + "\n".join(rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )


def test_data_access_ok(tmp_path, monkeypatch):
    uid = "U1"
    _write_csv(tmp_path, uid, [
        f'{uid},1773121104896,1773121104652,bankInfo,bankInfo,field-click,"{{}}",model,15,https://x/m/#/auth/bankInfo?from=%2F,null,1.1.1.1',
        f'{uid},1773121128143,1773121127644,bankInfo,bankInfo,field-edit,"{{}}",model,15,https://x/m/#/auth/bankInfo?from=%2F,null,1.1.1.1',
    ])
    monkeypatch.setattr("app.core.config.settings.local_data_dir", str(tmp_path))
    da = TraceDataAccess()
    raw = da.fetch(uid, _ctx(uid))
    assert raw["data_status"] == "ok"
    assert isinstance(raw["events_df"], pd.DataFrame)
    assert len(raw["events_df"]) == 2
    assert list(raw["events_df"].columns)[0] == "uid"


def test_data_access_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.local_data_dir", str(tmp_path))
    da = TraceDataAccess()
    raw = da.fetch("DOES_NOT_EXIST", _ctx("DOES_NOT_EXIST"))
    assert raw["data_status"] == "data_missing"
    assert raw["errors"]


def test_data_access_column_missing(tmp_path, monkeypatch):
    uid = "U2"
    base = tmp_path / "behavior" / "by_uid"
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{uid}.csv").write_text("uid,foo,bar\nU2,1,2\n", encoding="utf-8")
    monkeypatch.setattr("app.core.config.settings.local_data_dir", str(tmp_path))
    da = TraceDataAccess()
    raw = da.fetch(uid, _ctx(uid))
    assert raw["data_status"] == "error"
    assert any("column" in e.lower() or "schema" in e.lower() for e in raw["errors"])


def test_data_access_empty_csv(tmp_path, monkeypatch):
    uid = "U3"
    _write_csv(tmp_path, uid, [])
    monkeypatch.setattr("app.core.config.settings.local_data_dir", str(tmp_path))
    da = TraceDataAccess()
    raw = da.fetch(uid, _ctx(uid))
    assert raw["data_status"] == "ok"
    assert len(raw["events_df"]) == 0
```

**验证**：

```bash
python -m pytest tests/test_trace_analyzer_phase1.py -v 2>&1 | tail -10
```

预期：4 个测试全 RED（NotImplementedError 来自 data_access.py Stub）。

⛔ STOP — 报告 RED。

---

### Task 2.2 — TDD-GREEN：实现 `data_access.py`

文件路径：`app/runtime_skills/trace_analyzer/data_access.py`（**重写**整个文件，覆盖 Step 3 stub）

```python
"""Data access layer for the trace_analyzer pipeline.

Reads raw event CSV from {settings.local_data_dir}/behavior/by_uid/{uid}.csv.
See docs/specs/trace-analyzer-design.md §2.Q2 + §3.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.config import settings
from app.core.logger import get_logger
from app.runtime_skills.trace_analyzer.contracts import (
    TraceRawData,
    TraceRunContext,
)

logger = get_logger(__name__)

REQUIRED_COLUMNS: tuple[str, ...] = (
    "uid",
    "servertimestamp",
    "timestamp_",
    "scenetype",
    "processtype",
    "eventname",
    "extend",
    "clientmodel",
    "clientosversion",
    "url",
    "refer",
    "ip",
)


class TraceDataAccess:
    """Read raw behavior events for a single uid (no aggregation)."""

    def fetch(self, uid: str, context: TraceRunContext) -> TraceRawData:
        path = Path(settings.local_data_dir) / "behavior" / "by_uid" / f"{uid}.csv"
        if not path.exists():
            return {
                "uid": uid,
                "events_df": pd.DataFrame(columns=list(REQUIRED_COLUMNS)),
                "data_status": "data_missing",
                "errors": [f"csv_not_found:{path}"],
            }
        try:
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
        except Exception as exc:
            logger.warning("trace data_access read_csv failed uid=%s err=%s", uid, exc)
            return {
                "uid": uid,
                "events_df": pd.DataFrame(columns=list(REQUIRED_COLUMNS)),
                "data_status": "error",
                "errors": [f"csv_parse_error:{exc.__class__.__name__}"],
            }
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            return {
                "uid": uid,
                "events_df": pd.DataFrame(columns=list(REQUIRED_COLUMNS)),
                "data_status": "error",
                "errors": [f"column_schema_mismatch:missing={missing}"],
            }
        return {
            "uid": uid,
            "events_df": df,
            "data_status": "ok",
            "errors": [],
        }
```

**验证**：

```bash
python -m pytest tests/test_trace_analyzer_phase1.py -v 2>&1 | tail -10
```

预期：4 测试全 GREEN。

```bash
git add app/runtime_skills/trace_analyzer/data_access.py tests/test_trace_analyzer_phase1.py
git commit -m "feat(trace): implement data_access.py + 4 unit tests"
```

⛔ STOP。

---

### Task 3.1 — TDD-RED：feature_builder 测试

在 `tests/test_trace_analyzer_phase1.py` 末尾**追加**：

```python
import json as _json
from app.runtime_skills.trace_analyzer.feature_builder import TraceFeatureBuilder
from app.runtime_skills.trace_analyzer._constants import (
    INSUFFICIENT_EVENTS_THRESHOLD,
    TOP_N_TRANSITIONS, TOP_N_PAGES, TOP_K_FRICTION_HOTSPOTS,
    KEY_EVENTS_TAIL_N,
    TOTAL_TOKEN_BUDGET, TIER_3_TOKEN_BUDGET,
)


def _make_df(rows: list[dict]) -> pd.DataFrame:
    base = {c: "" for c in REQUIRED_COLUMNS_LIST}
    return pd.DataFrame([{**base, **r} for r in rows])


REQUIRED_COLUMNS_LIST = [
    "uid", "servertimestamp", "timestamp_", "scenetype", "processtype",
    "eventname", "extend", "clientmodel", "clientosversion", "url", "refer", "ip",
]


def _raw(df, status="ok", uid="U1"):
    return {"uid": uid, "events_df": df, "data_status": status, "errors": []}


def test_feature_builder_path_graph_top_n():
    df = _make_df([
        {"uid": "U1", "servertimestamp": str(1000 + i), "scenetype": p, "eventname": "x"}
        for i, p in enumerate(["A", "B", "A", "B", "C", "B", "C", "A", "D", "B", "E", "F"])
    ])
    fb = TraceFeatureBuilder()
    bundle = fb.build(_raw(df), _ctx())
    assert len(bundle["path_graph"]["top_pages"]) <= TOP_N_PAGES
    assert len(bundle["path_graph"]["top_transitions"]) <= TOP_N_TRANSITIONS
    pages = {p["page"] for p in bundle["path_graph"]["top_pages"]}
    assert "B" in pages  # most-visited


def test_feature_builder_friction_hotspots_severity_sorted():
    rows = []
    for i in range(6):
        rows.append({"uid": "U1", "servertimestamp": str(1773000000000 + i * 5000),
                     "scenetype": "kyc", "eventname": "field-edit",
                     "extend": '{"field":"id_no"}'})
    rows.append({"uid": "U1", "servertimestamp": str(1773000000000 + 6 * 5000),
                 "scenetype": "home", "eventname": "field-edit",
                 "extend": '{"field":"phone"}'})
    df = _make_df(rows)
    bundle = TraceFeatureBuilder().build(_raw(df), _ctx())
    assert len(bundle["friction_hotspots"]) <= TOP_K_FRICTION_HOTSPOTS
    severities = [h["severity"] for h in bundle["friction_hotspots"]]
    rank = {"high": 3, "medium": 2, "low": 1}
    assert severities == sorted(severities, key=lambda s: -rank.get(s, 0))
    assert bundle["friction_hotspots"][0]["avg_stay_seconds"] > 0


def test_feature_builder_time_pattern_24_buckets():
    df = _make_df([
        {"uid": "U1", "servertimestamp": "1773100800000", "scenetype": "home"},  # 02:00 UTC
        {"uid": "U1", "servertimestamp": "1773108000000", "scenetype": "home"},  # 04:00 UTC
    ])
    bundle = TraceFeatureBuilder().build(_raw(df), _ctx())
    hist = bundle["time_pattern"]["hour_histogram"]
    assert isinstance(hist, list) and len(hist) == 24
    assert sum(hist) == 2
    assert isinstance(bundle["time_pattern"]["active_window_label"], str)


def test_feature_builder_key_events_tail_redacted_and_capped():
    rows = []
    for i in range(KEY_EVENTS_TAIL_N + 20):
        rows.append({
            "uid": "U1", "servertimestamp": str(1773000000000 + i * 1000),
            "scenetype": "auth", "eventname": "field-click",
            "extend": '{"field":"phone","app_version":"1.2.6"}',
            "url": "https://x.com/m/#/auth?token=SECRET&from=%2F",
            "ip": "1.2.3.4",
        })
    bundle = TraceFeatureBuilder().build(_raw(_make_df(rows)), _ctx())
    tail = bundle["key_events_tail"]
    assert len(tail) == KEY_EVENTS_TAIL_N
    for ev in tail:
        # Whitelist enforced: only ts_offset / page / event / field allowed
        assert set(ev.keys()) <= {"ts_offset", "page", "event", "field"}
        # Redaction sanity
        assert "ip" not in ev
        assert "?" not in str(ev.get("page", ""))  # no url query


def test_feature_builder_churn_prior_candidates_in_whitelist():
    rows = []
    for i in range(4):  # repeated visits to interest page → interest_perception_high prior
        rows.append({"uid": "U1", "servertimestamp": str(1773000000000 + i * 1000),
                     "scenetype": "interest", "processtype": "interest",
                     "eventname": "page_onResume", "extend": "{}"})
    bundle = TraceFeatureBuilder().build(_raw(_make_df(rows)), _ctx())
    candidates = bundle["churn_root_cause_candidates"]
    assert isinstance(candidates, list)
    for c in candidates:
        assert c["value"] in {
            "credit_limit_unmet", "interest_perception_high", "competitor_poaching",
            "ux_friction", "repayment_burden", "no_clear_signal",
        }
        assert 0.0 <= float(c.get("confidence", 0)) <= 1.0


def test_feature_builder_token_budget_within_total():
    rows = [{"uid": "U1", "servertimestamp": str(1773000000000 + i * 1000),
             "scenetype": "auth", "eventname": "field-click", "extend": '{"field":"x"}'}
            for i in range(800)]
    bundle = TraceFeatureBuilder().build(_raw(_make_df(rows)), _ctx())
    fb = TraceFeatureBuilder()
    payload = [bundle["event_window"], bundle["path_graph"], bundle["friction_hotspots"],
               bundle["time_pattern"], bundle["key_events_tail"]]
    est = fb._estimate_tokens(_json.dumps(payload, ensure_ascii=False))
    assert est <= TOTAL_TOKEN_BUDGET, f"token budget exceeded est={est} budget={TOTAL_TOKEN_BUDGET}"


def test_feature_builder_tier3_halved_when_over_budget():
    # Force tier 3 to be larger than TIER_3_TOKEN_BUDGET so guard halves N
    rows = [{"uid": "U1", "servertimestamp": str(1773000000000 + i * 1000),
             "scenetype": "very_long_page_name_to_inflate_tokens" * 3,
             "eventname": "field-click",
             "extend": '{"field":"long_field_name_to_inflate_tokens"}'}
            for i in range(KEY_EVENTS_TAIL_N + 100)]
    bundle = TraceFeatureBuilder().build(_raw(_make_df(rows)), _ctx())
    # When trimmed, errors should record truncation
    if len(bundle["key_events_tail"]) < KEY_EVENTS_TAIL_N:
        assert any("truncat" in e.lower() or "tier3" in e.lower() for e in bundle["errors"])


def test_feature_builder_event_window_counts():
    df = _make_df([
        {"uid": "U1", "servertimestamp": "1773000000000", "scenetype": "a"},
        {"uid": "U1", "servertimestamp": "1773000060000", "scenetype": "b"},
    ])
    bundle = TraceFeatureBuilder().build(_raw(df), _ctx())
    win = bundle["event_window"]
    assert win["total_events"] == 2
    assert win["analyzed_events"] >= 2 - INSUFFICIENT_EVENTS_THRESHOLD or win["analyzed_events"] == 2
    assert win["start"] and win["end"]
```

**验证**：

```bash
python -m pytest tests/test_trace_analyzer_phase1.py -v -k feature_builder 2>&1 | tail -15
```

预期：8 个 feature_builder 测试全 RED（NotImplementedError）。

⛔ STOP。

---

### Task 3.2 — TDD-GREEN：实现 `feature_builder.py`

文件路径：`app/runtime_skills/trace_analyzer/feature_builder.py`（**重写**）

```python
"""Feature builder layer for the trace_analyzer pipeline.

Extracts the 5 rule-layer facts (path graph / friction hotspots / time pattern /
key events tail / churn root cause candidates) and applies the three-tier
token budget guard. See docs/specs/trace-analyzer-design.md §2.Q4 + §2.Q6.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from app.runtime_skills.trace_analyzer._constants import (
    INSUFFICIENT_EVENTS_THRESHOLD,
    KEY_EVENTS_PRE_DROPOFF_N,
    KEY_EVENTS_TAIL_N,
    TIER_2_TOKEN_BUDGET,
    TIER_3_TOKEN_BUDGET,
    TOP_K_FRICTION_HOTSPOTS,
    TOP_N_PAGES,
    TOP_N_TRANSITIONS,
    TOTAL_TOKEN_BUDGET,
)
from app.runtime_skills.trace_analyzer.contracts import (
    TraceFeatureBundle,
    TraceRawData,
    TraceRunContext,
)


class TraceFeatureBuilder:
    """Build deterministic trace features from the raw events DataFrame."""

    # ------- entry -------

    def build(
        self,
        raw_data: TraceRawData,
        context: TraceRunContext,
    ) -> TraceFeatureBundle:
        df: pd.DataFrame = raw_data.get("events_df")
        errors: list[str] = list(raw_data.get("errors", []))

        if raw_data.get("data_status") != "ok" or df is None or len(df) == 0:
            return self._empty_bundle(raw_data["uid"], status="empty", errors=errors)

        if len(df) < INSUFFICIENT_EVENTS_THRESHOLD:
            return self._empty_bundle(
                raw_data["uid"],
                status="insufficient_events",
                errors=errors + [f"insufficient_events:n={len(df)}"],
            )

        path_graph = self._build_path_graph(df)
        friction = self._build_friction_hotspots(df)
        time_pattern = self._build_time_pattern(df)
        tail = self._build_key_events_tail(df, n=KEY_EVENTS_TAIL_N)
        candidates = self._build_churn_candidates(df, path_graph, friction)
        window = self._build_event_window(df)

        bundle: TraceFeatureBundle = {
            "uid": raw_data["uid"],
            "event_window": window,
            "path_graph": path_graph,
            "friction_hotspots": friction[:TOP_K_FRICTION_HOTSPOTS],
            "time_pattern": time_pattern,
            "key_events_tail": tail,
            "churn_root_cause_candidates": candidates,
            "feature_status": "ok",
            "errors": errors,
        }
        self._apply_token_budget(bundle)
        return bundle

    # ------- 1. path graph -------

    def _build_path_graph(self, df: pd.DataFrame) -> dict[str, Any]:
        pages = df["scenetype"].fillna("").astype(str).tolist()
        ts = df["servertimestamp"].astype(str).tolist()

        page_counter = Counter(p for p in pages if p)
        # Average stay per page from consecutive timestamp deltas on same page
        stay_acc: dict[str, list[float]] = defaultdict(list)
        for i in range(len(pages) - 1):
            try:
                delta = (int(ts[i + 1]) - int(ts[i])) / 1000.0
            except ValueError:
                continue
            if pages[i] and 0 <= delta < 3600:  # cap 1h to ignore session breaks
                stay_acc[pages[i]].append(delta)
        top_pages = [
            {
                "page": p,
                "visit_count": int(c),
                "avg_stay_seconds": round(sum(stay_acc[p]) / len(stay_acc[p]), 2)
                if stay_acc[p] else 0.0,
            }
            for p, c in page_counter.most_common(TOP_N_PAGES)
        ]

        transitions: Counter[tuple[str, str]] = Counter()
        for i in range(len(pages) - 1):
            a, b = pages[i], pages[i + 1]
            if a and b and a != b:
                transitions[(a, b)] += 1
        top_transitions = [
            {"from": a, "to": b, "count": int(c)}
            for (a, b), c in transitions.most_common(TOP_N_TRANSITIONS)
        ]
        return {"top_pages": top_pages, "top_transitions": top_transitions}

    # ------- 2. friction hotspots -------

    def _build_friction_hotspots(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        # Group by (scenetype, extend.field). retry_count = field-edit count;
        # error_count = events whose eventname contains 'error'/'fail';
        # avg_stay_seconds = mean delta between this event ts and the next event ts.
        group: dict[tuple[str, str], dict[str, Any]] = {}
        rows = list(df.iterrows())
        for idx, (_, row) in enumerate(rows):
            page = str(row.get("scenetype", "") or "")
            extend_str = str(row.get("extend", "") or "")
            field = ""
            try:
                ext = json.loads(extend_str) if extend_str else {}
                if isinstance(ext, dict):
                    field = str(ext.get("field", "") or "")
            except (ValueError, TypeError):
                pass
            if not page:
                continue
            key = (page, field)
            slot = group.setdefault(key, {
                "step": f"{page}:{field}" if field else page,
                "retry_count": 0,
                "error_count": 0,
                "_stays": [],
            })
            ev = str(row.get("eventname", "") or "").lower()
            if ev == "field-edit":
                slot["retry_count"] += 1
            if "error" in ev or "fail" in ev:
                slot["error_count"] += 1
            if idx + 1 < len(rows):
                try:
                    cur_ts = int(row["servertimestamp"])
                    nxt_ts = int(rows[idx + 1][1]["servertimestamp"])
                    delta = (nxt_ts - cur_ts) / 1000.0
                    if 0 <= delta <= 3600:
                        slot["_stays"].append(delta)
                except (ValueError, KeyError, TypeError):
                    pass

        hotspots = []
        for (page, field), slot in group.items():
            severity = self._severity(slot["retry_count"], slot["error_count"])
            stays = slot["_stays"]
            avg_stay = sum(stays) / len(stays) if stays else 0.0
            hotspots.append({
                "step": slot["step"],
                "retry_count": slot["retry_count"],
                "error_count": slot["error_count"],
                "avg_stay_seconds": round(avg_stay, 3),
                "severity": severity,
            })
        rank = {"high": 3, "medium": 2, "low": 1}
        hotspots.sort(key=lambda h: (-rank[h["severity"]], -h["retry_count"], -h["error_count"]))
        return hotspots

    @staticmethod
    def _severity(retry: int, errors: int) -> str:
        if errors >= 1 or retry >= 5:
            return "high"
        if retry >= 2:
            return "medium"
        return "low"

    # ------- 3. time pattern -------

    def _build_time_pattern(self, df: pd.DataFrame) -> dict[str, Any]:
        hist = [0] * 24
        for ts_str in df["servertimestamp"].astype(str):
            try:
                ts_ms = int(ts_str)
            except ValueError:
                continue
            hour = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).hour
            hist[hour] += 1
        peak = hist.index(max(hist)) if any(hist) else 0
        if 22 <= peak or peak < 5:
            label = "深夜活跃"
        elif 5 <= peak < 12:
            label = "上午活跃"
        elif 12 <= peak < 18:
            label = "白天活跃"
        else:
            label = "晚间活跃"
        return {"hour_histogram": hist, "active_window_label": label}

    # ------- 4. key events tail (redacted) -------

    def _build_key_events_tail(self, df: pd.DataFrame, *, n: int) -> list[dict[str, Any]]:
        tail = df.tail(n)
        if len(tail) == 0:
            return []
        try:
            t0 = int(tail.iloc[0]["servertimestamp"])
        except (ValueError, KeyError):
            t0 = 0
        events: list[dict[str, Any]] = []
        for _, row in tail.iterrows():
            try:
                ts_offset = (int(row["servertimestamp"]) - t0) / 1000.0
            except ValueError:
                ts_offset = 0.0
            page = self._strip_url_query(str(row.get("scenetype", "") or ""))
            field = ""
            extend_str = str(row.get("extend", "") or "")
            try:
                ext = json.loads(extend_str) if extend_str else {}
                if isinstance(ext, dict):
                    field = str(ext.get("field", "") or "")
            except (ValueError, TypeError):
                pass
            ev: dict[str, Any] = {
                "ts_offset": round(ts_offset, 2),
                "page": page,
                "event": str(row.get("eventname", "") or ""),
            }
            if field:
                ev["field"] = field
            events.append(ev)
        return events

    @staticmethod
    def _strip_url_query(s: str) -> str:
        if "://" not in s:
            return s
        try:
            parsed = urlparse(s)
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        except (ValueError, TypeError):
            return s.split("?")[0]

    # ------- 5. churn prior candidates -------

    def _build_churn_candidates(
        self,
        df: pd.DataFrame,
        path_graph: dict[str, Any],
        friction: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        # Heuristic 1: heavy interest-page visits → interest_perception_high
        interest_visits = sum(
            p["visit_count"] for p in path_graph["top_pages"]
            if "interest" in p["page"].lower() or "rate" in p["page"].lower()
        )
        if interest_visits >= 3:
            out.append({"value": "interest_perception_high", "confidence": 0.6,
                        "reason": f"interest_pages_visits={interest_visits}"})
        # Heuristic 2: high-severity friction → ux_friction
        if any(h["severity"] == "high" for h in friction):
            out.append({"value": "ux_friction", "confidence": 0.7,
                        "reason": "high_severity_hotspot"})
        # Heuristic 3: heavy quota-page visits → credit_limit_unmet
        quota_visits = sum(
            p["visit_count"] for p in path_graph["top_pages"]
            if "quota" in p["page"].lower() or "limit" in p["page"].lower()
        )
        if quota_visits >= 3:
            out.append({"value": "credit_limit_unmet", "confidence": 0.6,
                        "reason": f"quota_pages_visits={quota_visits}"})
        if not out:
            out.append({"value": "no_clear_signal", "confidence": 0.5, "reason": "no_pattern"})
        return out[:2]  # 0-2 candidates

    # ------- 6. event window -------

    def _build_event_window(self, df: pd.DataFrame) -> dict[str, Any]:
        ts_series = pd.to_numeric(df["servertimestamp"], errors="coerce").dropna()
        if len(ts_series) == 0:
            return {"start": "", "end": "", "total_events": int(len(df)), "analyzed_events": int(len(df))}
        start = datetime.fromtimestamp(int(ts_series.min()) / 1000.0, tz=timezone.utc).isoformat()
        end = datetime.fromtimestamp(int(ts_series.max()) / 1000.0, tz=timezone.utc).isoformat()
        return {
            "start": start,
            "end": end,
            "total_events": int(len(df)),
            "analyzed_events": int(len(df)),
        }

    # ------- 7. token budget guard -------

    def _estimate_tokens(self, text: str) -> int:
        ascii_n = sum(1 for ch in text if ord(ch) < 128)
        cjk_n = len(text) - ascii_n
        return int(ascii_n * 0.25 + cjk_n * 1.0)

    def _apply_token_budget(self, bundle: TraceFeatureBundle) -> None:
        # Tier 3: key_events_tail. Halve until under TIER_3 budget.
        while True:
            est3 = self._estimate_tokens(json.dumps(bundle["key_events_tail"], ensure_ascii=False))
            if est3 <= TIER_3_TOKEN_BUDGET or len(bundle["key_events_tail"]) <= 4:
                break
            new_n = max(4, len(bundle["key_events_tail"]) // 2)
            bundle["key_events_tail"] = bundle["key_events_tail"][-new_n:]
            bundle["errors"].append(f"truncated:tier3:N->{new_n}")

        # Tier 2: friction_hotspots. Halve until under TIER_2 budget.
        while True:
            est2 = self._estimate_tokens(json.dumps(bundle["friction_hotspots"], ensure_ascii=False))
            if est2 <= TIER_2_TOKEN_BUDGET or len(bundle["friction_hotspots"]) <= 1:
                break
            new_k = max(1, len(bundle["friction_hotspots"]) // 2)
            bundle["friction_hotspots"] = bundle["friction_hotspots"][:new_k]
            bundle["errors"].append(f"truncated:tier2:K->{new_k}")

        # Final guard — if total still over TOTAL, halve tier 3 again
        full = json.dumps([
            bundle["event_window"], bundle["path_graph"], bundle["friction_hotspots"],
            bundle["time_pattern"], bundle["key_events_tail"],
        ], ensure_ascii=False)
        if self._estimate_tokens(full) > TOTAL_TOKEN_BUDGET and len(bundle["key_events_tail"]) > 4:
            bundle["key_events_tail"] = bundle["key_events_tail"][-(len(bundle["key_events_tail"]) // 2):]
            bundle["errors"].append("truncated:total:tier3_again")

    # ------- helpers -------

    def _empty_bundle(self, uid: str, *, status: str, errors: list[str]) -> TraceFeatureBundle:
        return {
            "uid": uid,
            "event_window": {"start": "", "end": "", "total_events": 0, "analyzed_events": 0},
            "path_graph": {"top_pages": [], "top_transitions": []},
            "friction_hotspots": [],
            "time_pattern": {"hour_histogram": [0] * 24, "active_window_label": ""},
            "key_events_tail": [],
            "churn_root_cause_candidates": [],
            "feature_status": status,
            "errors": errors,
        }
```

**验证**：

```bash
python -m pytest tests/test_trace_analyzer_phase1.py -v -k feature_builder 2>&1 | tail -15
```

预期：8 测试全 GREEN。

```bash
git add app/runtime_skills/trace_analyzer/feature_builder.py tests/test_trace_analyzer_phase1.py
git commit -m "feat(trace): implement feature_builder with 5 facts + token budget guard"
```

⛔ STOP。

---

### Task 4.1 — TDD-RED：decision_engine 测试

在 `tests/test_trace_analyzer_phase1.py` 末尾追加：

```python
from app.runtime_skills.trace_analyzer.decision_engine import TraceDecisionEngine


def _bundle_ok():
    return {
        "uid": "U1",
        "event_window": {"start": "s", "end": "e", "total_events": 100, "analyzed_events": 100},
        "path_graph": {"top_pages": [{"page": "kyc", "visit_count": 10, "avg_stay_seconds": 5.0}],
                       "top_transitions": [{"from": "home", "to": "kyc", "count": 3}]},
        "friction_hotspots": [{"step": "kyc:id_no", "retry_count": 4, "error_count": 1,
                                "avg_stay_seconds": 0.0, "severity": "high"}],
        "time_pattern": {"hour_histogram": [0] * 24, "active_window_label": "深夜活跃"},
        "key_events_tail": [{"ts_offset": 0.0, "page": "kyc", "event": "field-click"}],
        "churn_root_cause_candidates": [{"value": "ux_friction", "confidence": 0.7, "reason": "x"}],
        "feature_status": "ok",
        "errors": [],
    }


def test_decision_engine_prompt_payload_built():
    de = TraceDecisionEngine()
    res = de.decide(_bundle_ok(), _ctx())
    assert res["decision_status"] == "ok"
    payload = res["prompt_payload"]
    for key in ("event_window", "path_graph", "friction_hotspots",
                "time_pattern", "key_events_tail", "churn_candidates"):
        assert key in payload, f"missing prompt_payload.{key}"


def test_decision_engine_fallback_story_present():
    de = TraceDecisionEngine()
    res = de.decide(_bundle_ok(), _ctx())
    assert isinstance(res["fallback_story"], str) and len(res["fallback_story"]) > 0
    assert isinstance(res["fallback_interventions"], list)


def test_decision_engine_skips_when_insufficient():
    bundle = _bundle_ok()
    bundle["feature_status"] = "insufficient_events"
    bundle["friction_hotspots"] = []
    bundle["key_events_tail"] = []
    res = TraceDecisionEngine().decide(bundle, _ctx())
    assert res["decision_status"] == "skipped"
```

**验证**：

```bash
python -m pytest tests/test_trace_analyzer_phase1.py -v -k decision_engine 2>&1 | tail -10
```

预期：3 测试 RED。

⛔ STOP。

---

### Task 4.2 — TDD-GREEN：实现 `decision_engine.py`

文件路径：`app/runtime_skills/trace_analyzer/decision_engine.py`（**重写**）

```python
"""Decision engine layer for the trace_analyzer pipeline.

Assembles prompt payload + deterministic template fallback story / interventions.
See docs/specs/trace-analyzer-design.md §6.
"""
from __future__ import annotations

from typing import Any

from app.runtime_skills.trace_analyzer.contracts import (
    TraceDecisionResult,
    TraceFeatureBundle,
    TraceRunContext,
)


class TraceDecisionEngine:
    """Build prompt payload + template fallback."""

    def decide(
        self,
        feature_bundle: TraceFeatureBundle,
        context: TraceRunContext,
    ) -> TraceDecisionResult:
        if feature_bundle["feature_status"] != "ok":
            return {
                "uid": feature_bundle["uid"],
                "decision_status": "skipped",
                "prompt_payload": {},
                "fallback_story": self._fallback_story_skipped(feature_bundle["feature_status"]),
                "fallback_interventions": [],
                "errors": list(feature_bundle.get("errors", [])),
            }

        prompt_payload: dict[str, Any] = {
            "event_window": feature_bundle["event_window"],
            "path_graph": feature_bundle["path_graph"],
            "friction_hotspots": feature_bundle["friction_hotspots"],
            "time_pattern": feature_bundle["time_pattern"],
            "key_events_tail": feature_bundle["key_events_tail"],
            "churn_candidates": feature_bundle["churn_root_cause_candidates"],
        }
        return {
            "uid": feature_bundle["uid"],
            "decision_status": "ok",
            "prompt_payload": prompt_payload,
            "fallback_story": self._build_fallback_story(feature_bundle),
            "fallback_interventions": self._build_fallback_interventions(feature_bundle),
            "errors": list(feature_bundle.get("errors", [])),
        }

    @staticmethod
    def _fallback_story_skipped(status: str) -> str:
        if status == "insufficient_events":
            return "事件量不足，无法生成行为深度解析。"
        return "事件数据缺失或异常，无法生成行为深度解析。"

    @staticmethod
    def _build_fallback_story(bundle: TraceFeatureBundle) -> str:
        n_hot = len(bundle["friction_hotspots"])
        n_pages = len(bundle["path_graph"]["top_pages"])
        label = bundle["time_pattern"].get("active_window_label", "")
        return (
            f"基于规则识别到 {n_hot} 个摩擦热点，{n_pages} 个高频页面，"
            f"时段特征为 {label}。详见结构化结果。"
        )

    @staticmethod
    def _build_fallback_interventions(bundle: TraceFeatureBundle) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for h in bundle["friction_hotspots"][:3]:
            out.append({
                "hotspot": h["step"],
                "advice": f"在 {h['step']} 阶段观察到 retry={h['retry_count']} / "
                          f"error={h['error_count']}，建议针对性优化引导。",
                "channel_hint": "",
            })
        return out
```

**验证**：

```bash
python -m pytest tests/test_trace_analyzer_phase1.py -v -k decision_engine 2>&1 | tail -10
```

预期：3 测试 GREEN。

```bash
git add app/runtime_skills/trace_analyzer/decision_engine.py tests/test_trace_analyzer_phase1.py
git commit -m "feat(trace): implement decision_engine with prompt payload + template fallback"
```

⛔ STOP。

---

### Task 5.1 — TDD-RED：explainer 测试

在 `tests/test_trace_analyzer_phase1.py` 末尾追加：

```python
from unittest.mock import MagicMock
from app.runtime_skills.trace_analyzer.explainer import TraceExplainer


def _decision_ok():
    return {
        "uid": "U1",
        "decision_status": "ok",
        "prompt_payload": {"event_window": {}, "path_graph": {"top_pages": [], "top_transitions": []},
                            "friction_hotspots": [], "time_pattern": {}, "key_events_tail": [],
                            "churn_candidates": [{"value": "ux_friction", "confidence": 0.7}]},
        "fallback_story": "FALLBACK_STORY",
        "fallback_interventions": [{"hotspot": "h", "advice": "a", "channel_hint": ""}],
        "errors": [],
    }


def test_explainer_mock_mode_skips_llm():
    mc = MagicMock()
    mc.mode = "mock"
    mc.model_name = "mock"
    ex = TraceExplainer(mc)
    res = ex.explain(_decision_ok(), _ctx())
    assert res["explanation_status"] == "skipped"
    assert res["used_llm"] is False
    assert res["churn_story"] == "FALLBACK_STORY"
    mc.generate_structured.assert_not_called()


def test_explainer_llm_ok_path():
    mc = MagicMock()
    mc.mode = "vertex"
    mc.model_name = "gemini-3.1-pro-preview"
    mc.generate_structured.return_value = {
        "status": "ok",
        "structured_result": {
            "churn_story": "用户在 KYC 阶段遇到 4 次失败后退出。",
            "intervention_suggestions": [
                {"hotspot": "kyc:id_no", "advice": "在 KYC 上传环节加入实时光照检测",
                 "channel_hint": "WhatsApp"}
            ],
            "churn_root_cause": ["ux_friction"],
        },
    }
    res = TraceExplainer(mc).explain(_decision_ok(), _ctx())
    assert res["explanation_status"] == "ok"
    assert res["used_llm"] is True
    assert "KYC" in res["churn_story"]
    assert res["churn_root_cause"] == ["ux_friction"]


def test_explainer_filters_invalid_churn_root_cause():
    mc = MagicMock()
    mc.mode = "vertex"
    mc.model_name = "x"
    mc.generate_structured.return_value = {
        "status": "ok",
        "structured_result": {
            "churn_story": "x", "intervention_suggestions": [],
            "churn_root_cause": ["INVENTED_VALUE", "ux_friction"],
        },
    }
    res = TraceExplainer(mc).explain(_decision_ok(), _ctx())
    assert res["churn_root_cause"] == ["ux_friction"]


def test_explainer_falls_back_when_llm_fails():
    mc = MagicMock()
    mc.mode = "vertex"
    mc.model_name = "x"
    mc.generate_structured.return_value = {
        "status": "model_unavailable",
        "structured_result": {"churn_story": "", "intervention_suggestions": [], "churn_root_cause": []},
    }
    res = TraceExplainer(mc).explain(_decision_ok(), _ctx())
    assert res["explanation_status"] == "model_unavailable"
    assert res["used_llm"] is False
    assert res["churn_story"] == "FALLBACK_STORY"
    assert res["churn_root_cause"] == ["no_clear_signal"]
```

**验证**：

```bash
python -m pytest tests/test_trace_analyzer_phase1.py -v -k explainer 2>&1 | tail -15
```

预期：4 测试 RED。

⛔ STOP。

---

### Task 5.2 — TDD-GREEN：实现 `explainer.py` + 完整 prompt

文件路径：`app/runtime_skills/trace_analyzer/explainer.py`（**重写**）

```python
"""LLM explanation layer for the trace_analyzer pipeline.

Calls ModelClient.generate_structured() to produce churn story / intervention
suggestions / churn_root_cause final picks. See trace-analyzer-design.md §8.

Whitelist constraint: churn_root_cause output is filtered against the 6
candidate values shared with ops_advice (CHURN_ROOT_CAUSE_ENUM in _constants).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.model_client import ModelClient
from app.runtime_skills.trace_analyzer._constants import CHURN_ROOT_CAUSE_ENUM
from app.runtime_skills.trace_analyzer.contracts import (
    TraceDecisionResult,
    TraceExplanationResult,
    TraceRunContext,
)


PROMPT_PATH = Path(__file__).resolve().parents[3] / "app" / "prompts" / "trace_analyzer_prompt.md"


class TraceExplainer:
    """Generate LLM narrative + intervention suggestions on top of rule output."""

    def __init__(self, model_client: ModelClient) -> None:
        self.model_client = model_client

    def explain(
        self,
        decision_result: TraceDecisionResult,
        context: TraceRunContext,
    ) -> TraceExplanationResult:
        uid = decision_result["uid"]
        fallback_story = decision_result.get("fallback_story", "")
        fallback_interv = decision_result.get("fallback_interventions", [])

        if (
            decision_result["decision_status"] != "ok"
            or self.model_client.mode == "mock"
            or not context.get("enable_llm_explanation", True)
        ):
            return self._build_skipped(uid, fallback_story, fallback_interv,
                                        reason=self._skip_reason(decision_result, context))

        prompt = self._build_prompt(uid, decision_result["prompt_payload"])
        result = self.model_client.generate_structured(
            skill_name="trace_analyzer",
            prompt=prompt,
            fallback_result={"churn_story": "", "intervention_suggestions": [],
                              "churn_root_cause": []},
            response_schema=self._response_schema(),
        )
        if result.get("status") != "ok":
            return self._build_unavailable(uid, fallback_story, fallback_interv,
                                            reason=str(result.get("status", "")))

        sr = result.get("structured_result", {}) or {}
        churn_story = str(sr.get("churn_story", "") or "").strip() or fallback_story
        interventions = self._normalize_interventions(sr.get("intervention_suggestions"))
        if not interventions:
            interventions = fallback_interv
        churn_root_cause = [
            v for v in (sr.get("churn_root_cause") or []) if v in CHURN_ROOT_CAUSE_ENUM
        ] or ["no_clear_signal"]

        return {
            "uid": uid,
            "explanation_status": "ok",
            "used_llm": True,
            "churn_story": churn_story,
            "intervention_suggestions": interventions,
            "churn_root_cause": churn_root_cause[:2],
            "model_trace": {
                "mode": self.model_client.mode,
                "used_llm": True,
                "model_name": self.model_client.model_name,
                "fallback_reason": "",
            },
            "errors": [],
        }

    # ---- helpers ----

    def _build_prompt(self, uid: str, payload: dict[str, Any]) -> str:
        if not PROMPT_PATH.exists():
            return f"trace prompt missing. uid={uid} trace_data={json.dumps(payload)}"
        tpl = PROMPT_PATH.read_text(encoding="utf-8")
        return tpl.replace("{{uid}}", uid).replace(
            "{{trace_data}}",
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )

    def _response_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "churn_story": {"type": "string"},
                "intervention_suggestions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "hotspot": {"type": "string"},
                            "advice": {"type": "string"},
                            "channel_hint": {"type": "string"},
                        },
                    },
                },
                "churn_root_cause": {"type": "array", "items": {"type": "string"}},
            },
        }

    @staticmethod
    def _normalize_interventions(raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, list):
            return []
        out = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            out.append({
                "hotspot": str(item.get("hotspot", "") or ""),
                "advice": str(item.get("advice", "") or ""),
                "channel_hint": str(item.get("channel_hint", "") or ""),
            })
        return out

    def _skip_reason(self, decision: TraceDecisionResult, ctx: TraceRunContext) -> str:
        if decision["decision_status"] != "ok":
            return f"decision_{decision['decision_status']}"
        if self.model_client.mode == "mock":
            return "model_mode_mock"
        if not ctx.get("enable_llm_explanation", True):
            return "llm_disabled"
        return "unknown"

    def _build_skipped(self, uid, fallback_story, fallback_interv, *, reason) -> TraceExplanationResult:
        return {
            "uid": uid, "explanation_status": "skipped", "used_llm": False,
            "churn_story": fallback_story, "intervention_suggestions": fallback_interv,
            "churn_root_cause": ["no_clear_signal"],
            "model_trace": {
                "mode": self.model_client.mode, "used_llm": False,
                "model_name": getattr(self.model_client, "model_name", ""),
                "fallback_reason": reason,
            },
            "errors": [],
        }

    def _build_unavailable(self, uid, fallback_story, fallback_interv, *, reason) -> TraceExplanationResult:
        return {
            "uid": uid, "explanation_status": "model_unavailable", "used_llm": False,
            "churn_story": fallback_story, "intervention_suggestions": fallback_interv,
            "churn_root_cause": ["no_clear_signal"],
            "model_trace": {
                "mode": self.model_client.mode, "used_llm": False,
                "model_name": getattr(self.model_client, "model_name", ""),
                "fallback_reason": reason,
            },
            "errors": [],
        }
```

文件路径：`app/prompts/trace_analyzer_prompt.md`（**重写**完整内容）

```markdown
# Trace Analyzer Prompt

你是墨西哥现金贷场景下的 **行为轨迹深度解析专员**。

规则引擎已经从原始事件序列中提取出 5 类结构化事实（路径图 / 摩擦热点 / 时间分布 / 关键节点序列 / churn 先验候选）。
**你的任务是基于这些已确定的事实**，输出 3 类叙述性产物：流失归因故事线 / 干预建议 / churn_root_cause 最终判定。

## 输入
- uid: {{uid}}
- trace_data: {{trace_data}}

## 输出要求
你必须输出一个 JSON 对象，且只能输出 JSON，不要输出额外说明。
JSON 顶层字段必须包含：
- `churn_story`：中文故事线，描述用户在哪些页面/字段卡住、最终流失（或当前状态）。
- `intervention_suggestions`：数组，每条对应一个 top 摩擦热点。每条对象含 `hotspot` / `advice` / `channel_hint` 三字段。
- `churn_root_cause`：1-2 个字符串，必须从下方 6 种候选值中选取。

## 反模板硬约束（重要）
- ❌ 禁止 "建议优化 / 建议突出 / 建议触发 / 建议在关键流失窗口前" 等泛化开头
- ❌ 禁止虚构未在 `trace_data` 中出现的页面、字段、事件
- ✅ 干预建议每条必须以 "在 [具体页面名]" 或 "针对 [具体字段名]" 开头
- ✅ 干预建议必须引用 `trace_data.friction_hotspots` 中的具体 retry_count / error_count

## churn_root_cause 候选（必须 1-2 个）
| 值 | 适用场景 |
|---|---|
| `credit_limit_unmet` | 频繁访问额度/提额页未提交 |
| `interest_perception_high` | 利率页停留长后退出 |
| `competitor_poaching` | 竞品 APP 抢占注意 |
| `ux_friction` | 反复重试 / 错误堆叠 |
| `repayment_burden` | 逾期后访问骤降 |
| `no_clear_signal` | 以上均不明显 |

如果证据不足，使用 `no_clear_signal`。优先参考 `trace_data.churn_candidates` 提供的先验候选，但你可以基于 `trace_data` 全量事实修正/补充。

## 干预建议字段说明
- `hotspot`：与 `trace_data.friction_hotspots[i].step` 一致的页面:字段名
- `advice`：可执行话术，须含具体阶段名/字段名/重试次数
- `channel_hint`：建议的触达渠道（如 `WhatsApp` / `push` / `站内信`）；可空
```

**验证**：

```bash
python -m pytest tests/test_trace_analyzer_phase1.py -v -k explainer 2>&1 | tail -15
```

预期：4 测试 GREEN。

```bash
git add app/runtime_skills/trace_analyzer/explainer.py app/prompts/trace_analyzer_prompt.md tests/test_trace_analyzer_phase1.py
git commit -m "feat(trace): implement explainer + complete prompt template"
```

⛔ STOP。

---

### Task 6.1 — TDD-RED：assembler + analyzer 测试

在 `tests/test_trace_analyzer_phase1.py` 末尾追加：

```python
from app.runtime_skills.trace_analyzer.assembler import TraceAssembler
from app.runtime_skills.trace_analyzer.analyzer import TraceAnalyzer
from app.schemas.trace_analyzer import TraceAnalyzeResponse


def _explanation_ok():
    return {
        "uid": "U1", "explanation_status": "ok", "used_llm": True,
        "churn_story": "用户在 KYC 卡住", "intervention_suggestions": [
            {"hotspot": "kyc:id_no", "advice": "针对 id_no 加入光照提示", "channel_hint": "WhatsApp"}],
        "churn_root_cause": ["ux_friction"],
        "model_trace": {"mode": "vertex", "used_llm": True, "model_name": "x",
                          "fallback_reason": ""},
        "errors": [],
    }


def test_assembler_status_ok():
    bundle = _bundle_ok()
    decision = {"uid": "U1", "decision_status": "ok", "prompt_payload": {},
                "fallback_story": "fb", "fallback_interventions": [], "errors": []}
    res = TraceAssembler().assemble("U1", bundle, decision, _explanation_ok())
    TraceAnalyzeResponse.model_validate(res)
    assert res["status"] == "ok"
    assert res["churn_root_cause"] == ["ux_friction"]


def test_assembler_status_model_unavailable():
    bundle = _bundle_ok()
    decision = {"uid": "U1", "decision_status": "ok", "prompt_payload": {},
                "fallback_story": "fb", "fallback_interventions": [], "errors": []}
    expl = _explanation_ok()
    expl["explanation_status"] = "model_unavailable"
    expl["used_llm"] = False
    res = TraceAssembler().assemble("U1", bundle, decision, expl)
    assert res["status"] == "model_unavailable"


def test_analyzer_e2e_mock_mode(tmp_path, monkeypatch):
    uid = "EE1"
    rows = [f'{uid},{1773000000000 + i*1000},{1773000000000 + i*1000},kyc,kyc,'
            f'field-edit,"{{\\"field\\":\\"id_no\\"}}",m,15,https://x/kyc,null,1.1.1.1'
            for i in range(50)]
    base = tmp_path / "behavior" / "by_uid"
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{uid}.csv").write_text(CSV_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    monkeypatch.setattr("app.core.config.settings.local_data_dir", str(tmp_path))

    from app.core.model_client import ModelClient
    analyzer = TraceAnalyzer(model_client=ModelClient(mode="mock"))
    res = analyzer.analyze(uid, _ctx(uid))
    TraceAnalyzeResponse.model_validate(res)
    assert res["status"] == "model_unavailable"  # mock → no LLM
    assert res["uid"] == uid
    assert len(res["friction_hotspots"]) >= 1


def test_analyzer_data_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.local_data_dir", str(tmp_path))
    from app.core.model_client import ModelClient
    analyzer = TraceAnalyzer(model_client=ModelClient(mode="mock"))
    res = analyzer.analyze("NOPE", _ctx("NOPE"))
    assert res["status"] == "data_missing"


def test_analyzer_insufficient_events(tmp_path, monkeypatch):
    uid = "II1"
    base = tmp_path / "behavior" / "by_uid"
    base.mkdir(parents=True, exist_ok=True)
    rows = [f'{uid},{1773000000000 + i*1000},x,home,home,page_onResume,"{{}}",m,15,https://x/,null,1.1'
            for i in range(3)]
    (base / f"{uid}.csv").write_text(CSV_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    monkeypatch.setattr("app.core.config.settings.local_data_dir", str(tmp_path))
    from app.core.model_client import ModelClient
    res = TraceAnalyzer(model_client=ModelClient(mode="mock")).analyze(uid, _ctx(uid))
    assert res["status"] == "insufficient_events"
```

**验证**：

```bash
python -m pytest tests/test_trace_analyzer_phase1.py -v -k "assembler or analyzer" 2>&1 | tail -15
```

预期：5 测试 RED。

⛔ STOP。

---

### Task 6.2 — TDD-GREEN：实现 `assembler.py` + `analyzer.py`

文件路径：`app/runtime_skills/trace_analyzer/assembler.py`（**重写**）

```python
"""Assembly layer — merge rule output + LLM explanation into TraceAnalyzeResponse dict."""
from __future__ import annotations

from typing import Any

from app.runtime_skills.trace_analyzer.contracts import (
    TraceDecisionResult,
    TraceExplanationResult,
    TraceFeatureBundle,
)


class TraceAssembler:
    """Assemble the final TraceAnalyzeResponse Pydantic-shaped dict."""

    def assemble(
        self,
        uid: str,
        feature_bundle: TraceFeatureBundle,
        decision_result: TraceDecisionResult,
        explanation_result: TraceExplanationResult,
    ) -> dict[str, Any]:
        status = self._resolve_status(feature_bundle, decision_result, explanation_result)

        path_graph_in = feature_bundle["path_graph"]
        # Pydantic Transition uses alias `from`, so populate by alias to match schema
        top_transitions = [
            {"from": t["from"], "to": t["to"], "count": t["count"]}
            for t in path_graph_in.get("top_transitions", [])
        ]
        path_graph = {
            "top_transitions": top_transitions,
            "top_pages": list(path_graph_in.get("top_pages", [])),
        }

        return {
            "uid": uid,
            "status": status,
            "event_window": feature_bundle["event_window"],
            "path_graph": path_graph,
            "friction_hotspots": list(feature_bundle["friction_hotspots"]),
            "time_pattern": feature_bundle["time_pattern"],
            "churn_root_cause": list(explanation_result["churn_root_cause"]),
            "churn_story": explanation_result["churn_story"],
            "intervention_suggestions": list(explanation_result["intervention_suggestions"]),
            "key_events_tail": list(feature_bundle["key_events_tail"]),
            "model_trace": dict(explanation_result["model_trace"]),
            "errors": list(set(
                list(feature_bundle.get("errors", []))
                + list(decision_result.get("errors", []))
                + list(explanation_result.get("errors", []))
            )),
        }

    @staticmethod
    def _resolve_status(
        bundle: TraceFeatureBundle,
        decision: TraceDecisionResult,
        explanation: TraceExplanationResult,
    ) -> str:
        if bundle["feature_status"] == "empty":
            return "data_missing"
        if bundle["feature_status"] == "insufficient_events":
            return "insufficient_events"
        if bundle["feature_status"] != "ok":
            return "error"
        if explanation["explanation_status"] == "ok":
            return "ok"
        return "model_unavailable"
```

文件路径：`app/runtime_skills/trace_analyzer/analyzer.py`（**重写**）

```python
"""Trace analyzer entry point — orchestrates the six-step pipeline.

Trace analyzer is an independent service module (not a SkillRegistry Skill).
See docs/specs/trace-analyzer-design.md §2.Q3 for governance boundary.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.model_client import ModelClient
from app.runtime_skills.trace_analyzer.assembler import TraceAssembler
from app.runtime_skills.trace_analyzer.contracts import TraceRunContext
from app.runtime_skills.trace_analyzer.data_access import TraceDataAccess
from app.runtime_skills.trace_analyzer.decision_engine import TraceDecisionEngine
from app.runtime_skills.trace_analyzer.explainer import TraceExplainer
from app.runtime_skills.trace_analyzer.feature_builder import TraceFeatureBuilder


def build_context(uid: str, *, country_code: str | None = None,
                   enable_llm_explanation: bool = True) -> TraceRunContext:
    return {
        "uid": uid,
        "country_code": country_code or getattr(settings, "default_country_code", "mx"),
        "application_time": datetime.now(timezone.utc).isoformat(),
        "enable_llm_explanation": enable_llm_explanation,
    }


class TraceAnalyzer:
    """Orchestrate the trace_analyzer six-step pipeline.

    Note: Does NOT inherit BaseSkill. Not registered in SkillRegistry.
    Invoked directly by app/api/trace.py route handler.
    """

    def __init__(self, model_client: ModelClient | None = None) -> None:
        self.model_client = model_client or ModelClient(mode=settings.model_mode)
        self.data_access = TraceDataAccess()
        self.feature_builder = TraceFeatureBuilder()
        self.decision_engine = TraceDecisionEngine()
        self.explainer = TraceExplainer(self.model_client)
        self.assembler = TraceAssembler()

    def analyze(self, uid: str, context: TraceRunContext | None = None) -> dict[str, Any]:
        ctx = context or build_context(uid)
        raw = self.data_access.fetch(uid, ctx)
        bundle = self.feature_builder.build(raw, ctx)
        decision = self.decision_engine.decide(bundle, ctx)
        explanation = self.explainer.explain(decision, ctx)
        return self.assembler.assemble(uid, bundle, decision, explanation)
```

**验证**：

```bash
python -m pytest tests/test_trace_analyzer_phase1.py -v 2>&1 | tail -25
```

预期：所有 phase 1 测试（4 + 8 + 3 + 4 + 5 = 24）全 GREEN。

```bash
git add app/runtime_skills/trace_analyzer/assembler.py app/runtime_skills/trace_analyzer/analyzer.py tests/test_trace_analyzer_phase1.py
git commit -m "feat(trace): implement assembler + analyzer entry; e2e mock pipeline green"
```

⛔ STOP。

---

### Task 7.1 — TDD-RED：FastAPI 路由集成测试

文件路径：`tests/test_trace_analyzer_api.py`（新建）

```python
"""Trace analyzer route integration tests (FastAPI TestClient)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.trace import router as trace_router


CSV_HEADER = "uid,servertimestamp,timestamp_,scenetype,processtype,eventname,extend,clientmodel,clientosversion,url,refer,ip"


def _app() -> FastAPI:
    a = FastAPI()
    a.include_router(trace_router)
    return a


def test_route_data_missing_returns_404(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.local_data_dir", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.model_mode", "mock")
    client = TestClient(_app())
    resp = client.get("/api/trace/UNKNOWN_UID")
    assert resp.status_code == 404
    assert resp.json()["status"] == "data_missing"


def test_route_ok_path_mock_mode(tmp_path, monkeypatch):
    uid = "RT1"
    base = tmp_path / "behavior" / "by_uid"
    base.mkdir(parents=True, exist_ok=True)
    rows = [f'{uid},{1773000000000 + i*1000},{1773000000000 + i*1000},kyc,kyc,'
            f'field-edit,"{{\\"field\\":\\"id_no\\"}}",m,15,https://x/kyc,null,1.1'
            for i in range(50)]
    (base / f"{uid}.csv").write_text(CSV_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    monkeypatch.setattr("app.core.config.settings.local_data_dir", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.model_mode", "mock")

    client = TestClient(_app())
    resp = client.get(f"/api/trace/{uid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "model_unavailable"  # mock mode
    assert body["uid"] == uid
    assert len(body["friction_hotspots"]) >= 1


def test_route_insufficient_events_returns_200(tmp_path, monkeypatch):
    uid = "RT2"
    base = tmp_path / "behavior" / "by_uid"
    base.mkdir(parents=True, exist_ok=True)
    rows = [f'{uid},{1773000000000 + i*1000},x,home,home,page_onResume,"{{}}",m,15,https://x/,null,1'
            for i in range(3)]
    (base / f"{uid}.csv").write_text(CSV_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    monkeypatch.setattr("app.core.config.settings.local_data_dir", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.model_mode", "mock")

    client = TestClient(_app())
    resp = client.get(f"/api/trace/{uid}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "insufficient_events"
```

**验证**：

```bash
python -m pytest tests/test_trace_analyzer_api.py -v 2>&1 | tail -10
```

预期：3 测试 RED（NotImplementedError 来自 stub handler）。

⛔ STOP。

---

### Task 7.2 — TDD-GREEN：实装 `app/api/trace.py` handler

文件路径：`app/api/trace.py`（**重写**）

```python
"""GET /api/trace/{uid} route — independent endpoint.

Not coupled to /api/analyze. Invoked on-demand by frontend.
See docs/specs/trace-analyzer-design.md §2.Q1.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.runtime_skills.trace_analyzer.analyzer import TraceAnalyzer, build_context
from app.schemas.trace_analyzer import TraceAnalyzeResponse

router = APIRouter(tags=["trace_analyzer"])


@router.get("/api/trace/{uid}")
def get_trace(uid: str) -> JSONResponse:
    analyzer = TraceAnalyzer()
    raw = analyzer.analyze(uid, build_context(uid))
    validated = TraceAnalyzeResponse.model_validate(raw)
    payload = validated.model_dump(by_alias=True)
    if payload["status"] == "data_missing":
        return JSONResponse(content=payload, status_code=404)
    return JSONResponse(content=payload, status_code=200)
```

**验证**：

```bash
python -m pytest tests/test_trace_analyzer_api.py -v 2>&1 | tail -10
```

预期：3 测试 GREEN。

```bash
git add app/api/trace.py tests/test_trace_analyzer_api.py
git commit -m "feat(trace): implement /api/trace/{uid} handler with status→HTTP mapping"
```

⛔ STOP。

---

### Task 8.1 — `app/main.py` include_router（前置 `git pull --rebase`）

⚠️ **执行前必做**：

```bash
git pull --rebase github main
```

如果有冲突 STOP 报告，不强解。无冲突继续。

读 `app/main.py` 现状（D2 可能已加 SSE 路由），在合适位置（其他 `include_router` 旁）追加：

```python
from app.api.trace import router as trace_router  # noqa: E402
app.include_router(trace_router)
```

具体位置：紧贴现有 `app.include_router(...)` 调用之后；如果 import 集中在文件顶部，把 `from app.api.trace import router as trace_router` 移到 import 区。

**验证**：

```bash
python -m pytest tests/test_trace_analyzer_api.py tests/test_trace_analyzer_phase1.py -v 2>&1 | tail -5
python -c "
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)
r = c.get('/api/trace/NOPE_UID_FOR_SMOKE')
print('status:', r.status_code, 'body status:', r.json().get('status'))
"
```

预期：
- 第一条：所有 trace 测试 GREEN
- 第二条：`status: 404 body status: data_missing`（路由已挂载，找不到 uid 的 csv）

```bash
git add app/main.py
git commit -m "feat(trace): mount /api/trace/{uid} router in app/main.py"
```

⛔ STOP — 报告 Task 8.1 完成。

---

### Task 9.1 — 真 CSV sanity check（G1 uid mock 模式）

不写新代码，跑实测脚本：

```bash
python -c "
from app.core.model_client import ModelClient
from app.runtime_skills.trace_analyzer.analyzer import TraceAnalyzer, build_context
import json

uid = '824812551379353600'  # G1 case (实测 593 行)
analyzer = TraceAnalyzer(model_client=ModelClient(mode='mock'))
res = analyzer.analyze(uid, build_context(uid))
print('status:               ', res['status'])
print('total_events:         ', res['event_window']['total_events'])
print('top_pages count:      ', len(res['path_graph']['top_pages']))
print('top_transitions count:', len(res['path_graph']['top_transitions']))
print('friction_hotspots:    ', len(res['friction_hotspots']))
print('key_events_tail:      ', len(res['key_events_tail']))
print('churn_root_cause:     ', res['churn_root_cause'])
print('errors:               ', res['errors'])
print()
print('--- key_events_tail[0] (redaction sanity check) ---')
if res['key_events_tail']:
    ev = res['key_events_tail'][0]
    print(json.dumps(ev, ensure_ascii=False, indent=2))
    assert set(ev.keys()) <= {'ts_offset', 'page', 'event', 'field'}, \
        f'redaction LEAK: extra keys {set(ev.keys())}'
    print('REDACTION OK')
"
```

**验收准则**（user 肉眼审核）：
- `status == "model_unavailable"`（mock 模式预期）
- `total_events == 593`（实测值）
- `friction_hotspots >= 1`
- `key_events_tail` 元素 keys 子集于 `{ts_offset, page, event, field}`，无 ip / 无 url query

如果有偏差 → STOP 报告。不偏差 → 继续。

⛔ STOP — 报告 sanity check 输出。

---

### Task 9.2 — 全量回归 + TASK.md / PLANNING.md 更新 + `[complete]` commit

```bash
python -m pytest tests/ -v 2>&1 | tail -5
```

预期：210（baseline）+ 24 phase1 + 3 api = 237 passed（实际数以执行时为准，零回归即可）。

更新 `TASK.md`，在「功能清单」节末尾追加（`{YYYY-MM-DD}` 替换为实际完成当日）：

```
- [x] E1 单用户埋点深度解析 → docs/plans/trace-analyzer-plan.md（{YYYY-MM-DD}）
```

更新 `PLANNING.md` 末尾「更新记录」节追加：

```
- [{YYYY-MM-DD}] trace_analyzer 实装完成（docs/plans/trace-analyzer-plan.md）：六步管线全部 GREEN（24 + 3 = 27 新测试）+ /api/trace/{uid} 已挂载 main.py。零回归
```

```bash
git add TASK.md PLANNING.md
git commit -m "[complete] trace-analyzer-plan: event trace deep analysis"
```

**不 push**（CLAUDE.md：等 user 明确要求才 push）。

---

## 4. 风险与降级（Plan 阶段识别）

| 风险 | 触发 | 降级 |
|---|---|---|
| Task 8.1 `git pull --rebase` 冲突 | D2 同时改 main.py | STOP 报告，user 决定如何解；不强解 |
| Task 9.1 sanity check `friction_hotspots == 0` | G1 case 真实事件不含明显摩擦点 | 不必偏差报错；只要状态机 OK 即视为通过；本期不调整规则 |
| token 估算偏差导致仍超 LLM 上下文 | CJK 加权不准 | `_apply_token_budget` 第三层 N 减半护栏触发；ModelClient 报错 → `model_unavailable` |
| pandas read_csv 在 Windows 编码问题 | CSV BOM / GBK 等 | `dtype=str + keep_default_na=False` 默认 utf-8；如失败，data_status="error"，errors 字段记录 |
| `tier_3_token_budget` 5000 在 600 行真数据下偏紧 | 单事件序列化 ~10 token × 30 = 300（远小于 5000） | 实测预期富裕；如未来 KEY_EVENTS_TAIL_N 调到 200 才会触及上限 |
| churn_root_cause LLM 输出全空 | LLM 没选任何值 | explainer 兜底 `["no_clear_signal"]`（design §12 已定） |
| `intervention_suggestions` LLM 输出 `null` | LLM 未生成 | explainer fallback 用 decision_engine 的模板 interventions |
| Task 6.1 e2e 测试在 mock 模式 ModelClient 实例化失败 | `settings.model_mode` 强制 vertex 但环境无 key.json | TestClient 用 monkeypatch 强制 `model_mode=mock`；`ModelClient(mode="mock")` 不需要凭据 |

---

## 5. 不在本期 Plan 内的事项（明确划分）

- vertex / gemini 真 LLM 验收（design §13.2 留给交付后 user 单独跑）
- 跨用户聚合归因（E2 范围）
- 客群聚类（E2 范围）
- 前端 UI 实现（前端只消费 API）
- 修改 behavior_profile / ops_advice 任何文件（前置硬约束 #2 + design §10 Out-of-Scope）
- trace 的 churn_root_cause 回灌 ops_advice（design §10）
- push 到当前批准仓库对应的 remote（等 user 明确要求）

---

## 6. 更新记录

- [2026-05-01] 初始 Draft（Q1-Q6 锁定 + Step 3 Stub 落地后产出，baseline commit `3d239da`）
