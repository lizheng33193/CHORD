# Golden Test Plan — behavior + comprehensive 回归基线

- 状态：Draft（待 user 五点检查法审核）
- 关联 Design Doc：[docs/specs/golden-test-design.md](../specs/golden-test-design.md)
- Plan 名：`golden-test-plan`
- 基线 commit：`[baseline] golden-test-plan`
- 完成 commit 标注：`[complete] golden-test-plan: evaluation framework`

---

## 0. 关键事实勘察（Plan 写作前已查清，不在 Task 内）

| 事实 | 实际值 | 影响 |
|---|---|---|
| BehaviorProfile schema 类名 | `BehaviorProfileStructuredResult`（在 `app/schemas/behavior_profile.py:42`） | L1 import 用真实类名 |
| ComprehensiveProfile schema 类名 | `ComprehensiveProfileStructuredResult`（在 `app/schemas/comprehensive_profile.py:19`） | 同上 |
| `churn_root_cause` 字段位置 | 不在 schema 顶层；在 `feature_bundle` / decision_engine / explainer 内部流转，落到 `AgentOutput` 后路径需 baseline fixture 录完后实测 | L2 字段断言路径必须在录完 fixture 后写死，不能提前硬编码 |
| `recommended_segment` 字段位置 | `ComprehensiveProfileStructuredResult` schema 里没字面字段；可能落在 `tags` 或 `metrics` | 同上 |
| `tests/conftest.py` | 不存在 | Plan 要新建 |
| `tests/golden/` 目录 | 不存在 | Plan 要新建 |
| Skill 调用签名 | `BehaviorProfileSkill.analyze(uid, **kwargs)`，kwargs 接收 `repository`；`ComprehensiveProfileSkill.analyze(uid, **kwargs)`，kwargs 接收 `app_profile_result` / `behavior_profile_result` / `credit_profile_result` / `application_time` | runner 必须先跑 stage 0 三个再传给 comprehensive |
| ModelClient 切换方式 | `ModelClient(mode="vertex" \| "gemini" \| "mock")`，mode 来自 `settings.model_mode` | refresh 模式临时覆盖 |
| Repository | `LocalUserRepository`（基于 `data/` 目录） | runner 实例化它即可 |

**Plan 顺序调整说明**（相对 Design Doc §8）：
- Design Doc §8 把 "baseline 录制" 放在第 8 步（L1/L2/L3 实现之后）
- Plan 把它**提前**到 L2 实现之前（Task 4 之后）—— 因为 `churn_root_cause` / `recommended_segment` 真实字段路径需要从 fixture 反推，路径不知道就写不出 L2 断言
- L1 结构断言用 schema 的 `model_validate`，不依赖具体字段路径，可以先写

---

## 1. Plan 总览

| Phase | Task | 内容 | 预估 | 验证 |
|---|---|---|---|---|
| 0 | 0.1 | 基线 commit | 1 min | `git log --oneline -1` |
| 1 | 1.1 | 新建 `tests/conftest.py` 注册 `--refresh-fixtures` flag → 独立 commit | 3 min | `pytest --refresh-fixtures --collect-only` |
| 1 | 1.2 | 新建 `tests/golden/__init__.py` + `tests/golden/runner.py` 骨架 + `GOLDEN_CASES` 注册表（含 3 个 NotImplementedError helper：churn/segment/advice） → 独立 commit | 5 min | `python -c "from tests.golden.runner import GOLDEN_CASES; print(len(GOLDEN_CASES))"` |
| 2 | 2.1 | TDD-RED：新建 `tests/test_golden_behavior_comprehensive.py`，4 behavior + 1 comprehensive 的 fixture-load 测试 | 3 min | 5 测试全红 |
| 2 | 2.2 | TDD-GREEN：runner 实现 `load_fixture` / `record_fixture` + L1 结构断言 → 独立 commit | 5 min | 5 测试 ERROR 在 `FileNotFoundError`（L1 OK，缺 fixture） |
| 3 | 3.1 | runner 实现 `run_skill_real_llm`（behavior 单 skill + comprehensive 串 stage 0 三个） | 5 min | dry check：MODEL_MODE 非 mock |
| 3 | 3.2 | **首次 baseline 录制（real LLM）** + Python 审核脚本 + fixture 单独 commit | 5–10 min（含 LLM 调用） | 5 个 fixture 文件 status=ok |
| 4 | 4.1 | 跑 walker A/B/C → 反推 3 个 helper 真实路径（churn / segment / advice） | 5 min | 3 个 helper 实测取出预期类型 |
| 4 | 4.2 | TDD-RED：往 test 文件加 L2 字段断言调用 | 3 min | 5 测试全红 |
| 4 | 4.3 | TDD-GREEN：runner 实现 `assert_l2_fields` + `_L2_CHURN_COVERED` + 加 `test_l2_coverage_churn_root_cause` 守门测试 → 独立 commit | 7 min | 6 测试全绿（5 + coverage） |
| 5 | 5.1 | TDD-RED：加 L3 单 case 反向断言调用 | 3 min | 4 behavior 测试红 |
| 5 | 5.2 | TDD-GREEN：runner 实现 `assert_l3_content`（用 `get_business_advice` helper） | 4 min | 全绿 |
| 5 | 5.3 | TDD-RED：加 L3-d 跨 case 断言（G1 vs G3 quincena） | 3 min | 1 测试红 |
| 5 | 5.4 | TDD-GREEN：runner 实现 `assert_l3d_quincena_diff` → 独立 commit | 4 min | 全绿 |
| 6 | 6.1 | 不带 flag 重跑确认全绿 + 全量 `pytest tests/ -v` 零回归 | 3 min | 0 failed |
| 6 | 6.2 | 更新 PLANNING.md / TASK.md（A1 打勾，日期填执行当日）+ `[complete]` commit | 2 min | `git log --oneline -1` |

合计预估 ≈ 60–70 min（含 baseline 录制的 LLM 等待时间）。
独立 commit 数（不含 baseline / complete）：1.1 / 1.2 / 2.2 / 3.2(fixture) / 4.3 / 5.4 = 6 个 feat commit。

---

## 2. 五点检查法预审

| # | 检查项 | 自查 |
|---|---|---|
| 1 | 每个 Task 有精确文件路径？ | ✅ 全部到文件名级别 |
| 2 | 有占位符（TBD / TODO / implement later）？ | ✅ Plan 写作阶段无占位符。Task 1.2 骨架的 3 个 `NotImplementedError` 是**Test-First 设计的故意失败点**（让 RED 测试可识别），由 Task 4.1 walker 输出后写死真实路径。Task 4.1 代码模板中 `{... access path from walker X ...}` 是**显式标注的执行时填空**（非设计占位符），紧贴 walker 命令使用，不会被误执行 |
| 3 | 代码步骤有完整代码块？ | ✅ §3 提供完整代码块 |
| 4 | 有验证命令 + 预期输出？ | ✅ 每 Task 末尾"验证"一栏 |
| 5 | 一个人不问问题能执行完？ | ✅ 唯一例外：Task 3.2 baseline 录制后**显式 STOP** 等 user 肉眼审核 fixture（这是 Design Doc §8 第 8 步明示要求） |

---

## 3. 详细 Task 代码块

### Task 0.1 — 基线 commit

```bash
git commit --allow-empty -m "[baseline] golden-test-plan"
```

**验证**：`git log --oneline -1` 应显示 `[baseline] golden-test-plan`。

---

### Task 1.1 — 新建 `tests/conftest.py`

文件路径：`tests/conftest.py`（新建）

```python
"""Pytest config: register --refresh-fixtures flag for golden test recording."""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--refresh-fixtures",
        action="store_true",
        default=False,
        help="Re-record golden fixtures by calling real LLM. "
        "Use after intentional prompt changes; otherwise leave off so tests "
        "read from tests/fixtures/golden/.",
    )


@pytest.fixture
def refresh_fixtures(request: pytest.FixtureRequest) -> bool:
    return bool(request.config.getoption("--refresh-fixtures"))
```

**验证**：

```bash
pytest --refresh-fixtures --collect-only -q tests/ 2>&1 | head -5
```

预期：不报 "unrecognized arguments" 错误，正常 collect。

```bash
git add tests/conftest.py
git commit -m "feat(eval): register --refresh-fixtures pytest flag"
```

⛔ STOP — 报告 Task 1.1 完成。

---

### Task 1.2 — 新建 `tests/golden/runner.py` 骨架 + `GOLDEN_CASES` 注册表

文件路径：`tests/golden/__init__.py`（新建，空文件）

文件路径：`tests/golden/runner.py`（新建）

```python
"""Golden test runner: fixture I/O, real-LLM recording, three-layer assertions.

Three layers:
  L1 — Pydantic structure validation
  L2 — Field-level (non-empty / enum / length)
  L3 — Content reverse-regex (forbidden-template guard)

Fixture record/replay:
  Default: load from tests/fixtures/golden/{skill}/{uid}.json
  --refresh-fixtures: call real LLM, write fixture, skip assertions
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures" / "golden"


@dataclass
class GoldenCase:
    case_id: str
    uid: str
    selection_reason: str
    dimensions: list[str]
    skills: list[str]  # e.g. ["behavior_profile"] or ["behavior_profile", "comprehensive_profile"]
    quincena_class: str = ""  # "strong" | "weak" | "" — drives L3-d cross-case payday-narrative
                              # diff assertion (Task 5.4); G1 (strong) vs G3 (weak) are paired.


GOLDEN_CASES: list[GoldenCase] = [
    GoldenCase(
        case_id="G1",
        uid="824812551379353600",
        selection_reason="strong quincena (70%) + high event density (593) + multi-day span (9d); "
        "only triple-source-complete UID — also serves as comprehensive smoke",
        dimensions=["A", "C"],
        skills=["behavior_profile", "comprehensive_profile"],
        quincena_class="strong",
    ),
    GoldenCase(
        case_id="G2",
        uid="824822394441957376",
        selection_reason="extreme strong quincena (91%) + extreme high density (978)",
        dimensions=["A", "C"],
        skills=["behavior_profile"],
        quincena_class="strong",
    ),
    GoldenCase(
        case_id="G3",
        uid="824848564055179264",
        selection_reason="quincena counter-example (36%) — verifies prompt does not hallucinate "
        "payday narrative when signal is weak",
        dimensions=["B", "C"],
        skills=["behavior_profile"],
        quincena_class="weak",
    ),
    GoldenCase(
        case_id="G4",
        uid="824928257039138816",
        selection_reason="low density (234) + single day — verifies narrative does not degrade "
        "when token budget is ample",
        dimensions=["D"],
        skills=["behavior_profile"],
        quincena_class="strong",
    ),
]


def fixture_path(skill: str, uid: str) -> Path:
    return FIXTURE_ROOT / skill / f"{uid}.json"


def load_fixture(skill: str, uid: str) -> dict[str, Any]:
    p = fixture_path(skill, uid)
    if not p.exists():
        raise FileNotFoundError(
            f"Golden fixture missing: {p}. "
            f"Run: pytest tests/test_golden_behavior_comprehensive.py --refresh-fixtures"
        )
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def record_fixture(skill: str, uid: str, output: dict[str, Any]) -> None:
    p = fixture_path(skill, uid)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, sort_keys=True)


# --- Field-path helpers (Task 4.1 fills these in based on real fixture inspection) ---

def get_churn_root_cause(behavior_output: dict[str, Any]) -> list[str] | None:
    """Locate churn_root_cause in behavior AgentOutput. Implemented in Task 4.1."""
    raise NotImplementedError("Task 4.1 will fill in real path after baseline recording")


def get_recommended_segment(comprehensive_output: dict[str, Any]) -> str | None:
    """Locate recommended_segment in comprehensive AgentOutput. Implemented in Task 4.1."""
    raise NotImplementedError("Task 4.1 will fill in real path after baseline recording")


def get_business_advice(behavior_output: dict[str, Any]) -> list[str]:
    """Locate business_advice list in behavior AgentOutput. Implemented in Task 4.1."""
    raise NotImplementedError("Task 4.1 will fill in real path after baseline recording")


def get_behavior_summary(behavior_output: dict[str, Any]) -> str:
    """Read behavior_summary from evidence.behavior_profile_narrative."""
    return (
        behavior_output.get("structured_result", {})
        .get("evidence", {})
        .get("behavior_profile_narrative", {})
        .get("behavior_summary", "")
    )


# --- L1 / L2 / L3 assertion entry points (filled in later tasks) ---

def assert_l1_structure(skill: str, output: dict[str, Any]) -> None:
    raise NotImplementedError("Task 2.2")


def assert_l2_fields(case: GoldenCase, skill: str, output: dict[str, Any]) -> None:
    raise NotImplementedError("Task 4.3")


def assert_l3_content(case: GoldenCase, output: dict[str, Any]) -> None:
    raise NotImplementedError("Task 5.2")


def assert_l3d_quincena_diff(strong_case_output: dict[str, Any], weak_case_output: dict[str, Any]) -> None:
    raise NotImplementedError("Task 5.4")


# --- Real-LLM execution (Task 3.1) ---

def run_skill_real_llm(skill_name: str, uid: str) -> dict[str, Any]:
    raise NotImplementedError("Task 3.1")
```

**验证**：

```bash
python -c "from tests.golden.runner import GOLDEN_CASES; assert len(GOLDEN_CASES) == 4; print('OK', [c.case_id for c in GOLDEN_CASES])"
```

预期输出：`OK ['G1', 'G2', 'G3', 'G4']`

```bash
git add tests/golden/__init__.py tests/golden/runner.py
git commit -m "feat(eval): add golden runner skeleton + GOLDEN_CASES registry (G1-G4)"
```

⛔ STOP — 报告完成 Task 1.2，等 user 确认后做 Task 2.1。

---

### Task 2.1 — TDD-RED：写 fixture-load 测试

文件路径：`tests/test_golden_behavior_comprehensive.py`（新建）

```python
"""Golden tests for behavior_profile + comprehensive_profile regression baseline.

Run modes:
  Default (replay):       pytest tests/test_golden_behavior_comprehensive.py -v
  Refresh (real LLM):     pytest tests/test_golden_behavior_comprehensive.py -v --refresh-fixtures

See docs/specs/golden-test-design.md for layered assertion design.
"""

from __future__ import annotations

import pytest

from tests.golden.runner import (
    GOLDEN_CASES,
    GoldenCase,
    load_fixture,
    record_fixture,
    run_skill_real_llm,
    assert_l1_structure,
)


def _cases_for_skill(skill: str) -> list[GoldenCase]:
    return [c for c in GOLDEN_CASES if skill in c.skills]


@pytest.mark.parametrize("case", _cases_for_skill("behavior_profile"), ids=lambda c: f"{c.case_id}-{c.uid}")
def test_behavior_fixture_loadable(case: GoldenCase, refresh_fixtures: bool) -> None:
    if refresh_fixtures:
        output = run_skill_real_llm("behavior_profile", case.uid)
        record_fixture("behavior_profile", case.uid, output)
        return
    output = load_fixture("behavior_profile", case.uid)
    assert "structured_result" in output, f"{case.case_id}: AgentOutput missing structured_result"
    assert_l1_structure("behavior_profile", output)


@pytest.mark.parametrize("case", _cases_for_skill("comprehensive_profile"), ids=lambda c: f"{c.case_id}-{c.uid}")
def test_comprehensive_fixture_loadable(case: GoldenCase, refresh_fixtures: bool) -> None:
    if refresh_fixtures:
        output = run_skill_real_llm("comprehensive_profile", case.uid)
        record_fixture("comprehensive_profile", case.uid, output)
        return
    output = load_fixture("comprehensive_profile", case.uid)
    assert "structured_result" in output, f"{case.case_id}: AgentOutput missing structured_result"
    assert_l1_structure("comprehensive_profile", output)
```

**验证**：

```bash
pytest tests/test_golden_behavior_comprehensive.py -v 2>&1 | tail -20
```

预期：5 个测试 ID（G1/G2/G3/G4 behavior + G1 comprehensive）全部 FAILED 或 ERRORED（fixture 不存在 / `assert_l1_structure` NotImplementedError）。

⛔ STOP — 报告 RED 状态，等 user 确认后做 Task 2.2。

---

### Task 2.2 — TDD-GREEN：runner 实现 L1 + fixture I/O

修改 `tests/golden/runner.py`，把 `assert_l1_structure` 实现替换 `NotImplementedError`：

```python
def assert_l1_structure(skill: str, output: dict[str, Any]) -> None:
    """L1 — schema validates + AgentOutput four-key shape."""
    for required_key in ("summary", "structured_result", "charts", "report_markdown"):
        assert required_key in output, f"L1[{skill}]: missing AgentOutput key={required_key}"

    sr = output["structured_result"]
    if skill == "behavior_profile":
        from app.schemas.behavior_profile import BehaviorProfileStructuredResult
        BehaviorProfileStructuredResult.model_validate(sr)
    elif skill == "comprehensive_profile":
        from app.schemas.comprehensive_profile import ComprehensiveProfileStructuredResult
        ComprehensiveProfileStructuredResult.model_validate(sr)
    else:
        raise ValueError(f"Unknown skill in L1 assertion: {skill}")
```

**验证**：

```bash
pytest tests/test_golden_behavior_comprehensive.py -v 2>&1 | tail -20
```

预期：5 个测试现在 ERROR 在 `FileNotFoundError`（fixture 不存在），不再是 `NotImplementedError` —— 说明 L1 实现 OK，只差 fixture。

```bash
git add tests/golden/runner.py tests/test_golden_behavior_comprehensive.py
git commit -m "feat(eval): implement L1 schema validation + fixture I/O"
```

⛔ STOP — 报告：L1 已实现，下一步 Task 3.1 实现真实 LLM 调用。

---

### Task 3.1 — runner 实现 `run_skill_real_llm`

修改 `tests/golden/runner.py`，把 `run_skill_real_llm` 实现替换 `NotImplementedError`：

```python
def run_skill_real_llm(skill_name: str, uid: str) -> dict[str, Any]:
    """Run real-LLM skill (single uid). For comprehensive: also runs stage-0 three skills first.

    Caller must already have MODEL_MODE configured (vertex / gemini) via .env.
    """
    from app.core.config import settings
    from app.core.model_client import ModelClient
    from app.repositories.local_repository import LocalUserRepository
    from app.runtime_skills.app_profile_agent import AppProfileSkill
    from app.runtime_skills.behavior_profile_agent import BehaviorProfileSkill
    from app.runtime_skills.credit_profile_agent import CreditProfileSkill
    from app.runtime_skills.comprehensive_agent import ComprehensiveProfileSkill

    if settings.model_mode == "mock":
        raise RuntimeError(
            "Refusing to refresh golden fixtures in MODEL_MODE=mock. "
            "Set MODEL_MODE=vertex (or gemini) in .env before --refresh-fixtures."
        )

    client = ModelClient(mode=settings.model_mode)
    repo = LocalUserRepository()

    if skill_name == "behavior_profile":
        skill = BehaviorProfileSkill(client)
        return skill.analyze(uid, repository=repo)

    if skill_name == "comprehensive_profile":
        app_skill = AppProfileSkill(client)
        beh_skill = BehaviorProfileSkill(client)
        cre_skill = CreditProfileSkill(client)
        comp_skill = ComprehensiveProfileSkill(client)

        app_out = app_skill.analyze(uid, repository=repo)
        beh_out = beh_skill.analyze(uid, repository=repo)
        cre_out = cre_skill.analyze(uid, repository=repo)
        return comp_skill.analyze(
            uid,
            app_profile_result=app_out,
            behavior_profile_result=beh_out,
            credit_profile_result=cre_out,
        )

    raise ValueError(f"Unknown skill in run_skill_real_llm: {skill_name}")
```

**验证**：

```bash
python -c "
from tests.golden.runner import run_skill_real_llm
import os
print('MODEL_MODE =', os.environ.get('MODEL_MODE', '(unset)'))
"
```

预期：打印当前 MODEL_MODE，确认非 mock 模式（如果 mock 要先 `export MODEL_MODE=vertex` 或在 .env 改）。**不实际调 LLM**（dry check only）。

⛔ STOP — 报告：等 user 确认 MODEL_MODE 后做 Task 3.2 真录制。

---

### Task 3.2 — 首次 baseline 录制（real LLM）⚠️ 最关键的一步

```bash
pytest tests/test_golden_behavior_comprehensive.py -v --refresh-fixtures
```

预期：
- 跑 5 个测试（4 behavior + 1 comprehensive），每个调真实 LLM
- 总耗时 5–10 分钟（comprehensive 单 case 因为要带 stage 0 三个 skill 一起跑，~3 min；behavior 单 skill ~30s × 4 = 2 min）
- 5 个测试 PASSED（refresh 模式只录不评）
- 文件落地：
  - `tests/fixtures/golden/behavior_profile/824812551379353600.json`
  - `tests/fixtures/golden/behavior_profile/824822394441957376.json`
  - `tests/fixtures/golden/behavior_profile/824848564055179264.json`
  - `tests/fixtures/golden/behavior_profile/824928257039138816.json`
  - `tests/fixtures/golden/comprehensive_profile/824812551379353600.json`

录完后**肉眼审核**（user 必须做的，不能让 Claude 单方面通过）。审核脚本（Python，避免 PowerShell / bash 兼容性问题）：

```bash
python -c "
import json, glob, os
files = sorted(glob.glob('tests/fixtures/golden/behavior_profile/*.json')) + \
        sorted(glob.glob('tests/fixtures/golden/comprehensive_profile/*.json'))
for f in files:
    print(f'===== {f} =====')
    d = json.load(open(f, encoding='utf-8'))
    sr = d.get('structured_result', {})
    print(f'  status:           {sr.get(\"status\")}')
    print(f'  summary len:      {len(d.get(\"summary\", \"\"))}')
    print(f'  report_md len:    {len(d.get(\"report_markdown\", \"\"))}')
    print(f'  sr top keys:      {list(sr.keys())[:10]}')
"
```

**验证准则**（user 审核）：
- 每个 fixture `status == "ok"`（不是 `data_missing` / `model_unavailable`）
- `report_markdown` 长度 > 100
- `summary` 长度 > 20
- behavior fixture 的 `structured_result` 含 `evidence`（包含 `behavior_profile_narrative.behavior_summary`）

⛔⛔⛔ HARD STOP — user 必须肉眼审核 5 个 fixture 后明确说"通过"，才能做 Task 4.1。
如果 fixture 有质量问题（如某 case fall back to data_missing），STOP 并报告，可能要重选 UID 或修 prompt。

录制通过后 commit（fixture 单独一个 commit，便于 PR 审 fixture diff 时与代码改动分离）：

```bash
git add tests/fixtures/golden/
git commit -m "feat(eval): record initial golden fixtures (4 behavior + 1 comprehensive smoke)"
```

---

### Task 4.1 — 从 fixture 反推真实字段路径

修改 `tests/golden/runner.py` 中的 `get_churn_root_cause`、`get_recommended_segment`、`get_business_advice` 三个 helper —— **三个都还是 `NotImplementedError`**，本任务用 walker 跑 fixture 找出真实路径后再写死。

**严格流程**（不要凭猜测预填路径）：

1. 跑三个 walker 命令，把输出粘在汇报里给 user 看：

```bash
# Walker A — 找 churn_root_cause（behavior fixture）
python -c "
import json
d = json.load(open('tests/fixtures/golden/behavior_profile/824812551379353600.json', encoding='utf-8'))
sr = d['structured_result']
def walk(obj, path=''):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if 'churn' in k.lower() or 'root_cause' in k.lower():
                print(f'  FOUND at {path}.{k} = {v if not isinstance(v, (dict, list)) else type(v).__name__}')
            walk(v, f'{path}.{k}')
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk(v, f'{path}[{i}]')
walk(sr)
"
```

```bash
# Walker B — 找 recommended_segment / S1-S6（comprehensive fixture）
python -c "
import json, re
d = json.load(open('tests/fixtures/golden/comprehensive_profile/824812551379353600.json', encoding='utf-8'))
sr = d['structured_result']
def walk(obj, path=''):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and re.fullmatch(r'S[1-6]', v):
                print(f'  segment-like at {path}.{k} = {v}')
            if 'segment' in k.lower():
                print(f'  segment-key at {path}.{k} = {v if not isinstance(v, (dict, list)) else type(v).__name__}')
            walk(v, f'{path}.{k}')
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk(v, f'{path}[{i}]')
walk(sr)
"
```

```bash
# Walker C — 找 business_advice / suggestion / recommend（behavior fixture）
python -c "
import json
d = json.load(open('tests/fixtures/golden/behavior_profile/824812551379353600.json', encoding='utf-8'))
sr = d['structured_result']
def walk(obj, path=''):
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = k.lower()
            if 'advice' in kl or 'suggestion' in kl or 'recommend' in kl:
                kind = type(v).__name__
                preview = (v if isinstance(v, str) else (v[:2] if isinstance(v, list) else list(v.keys())[:5] if isinstance(v, dict) else v))
                print(f'  FOUND at {path}.{k}  ({kind})  preview={preview!r}')
            walk(v, f'{path}.{k}')
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk(v, f'{path}[{i}]')
walk(sr)
"
```

2. 根据 walker A/B/C 输出，把三个 helper 写死。**不要凭设计文档猜测路径**——以 walker 实际输出为准。代码模板（`{...}` 处替换为 walker 实测路径）：

```python
def get_churn_root_cause(behavior_output: dict[str, Any]) -> list[str] | None:
    """Path discovered from baseline fixture inspection (Task 4.1, walker A).

    Returns None if field absent (not all behavior cases must expose it).
    """
    sr = behavior_output.get("structured_result", {})
    # Replace {...} with actual path from walker A output, e.g.:
    #   val = sr.get("evidence", {}).get("churn_root_cause")
    val = {... access path from walker A ...}
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        return [val]
    return None


def get_recommended_segment(comprehensive_output: dict[str, Any]) -> str | None:
    """Path discovered from baseline fixture inspection (Task 4.1, walker B)."""
    sr = comprehensive_output.get("structured_result", {})
    # Replace with actual path from walker B output, e.g.:
    #   - direct field: sr.get("recommended_segment")
    #   - nested:       sr.get("metrics", {}).get("recommended_segment")
    #   - tag scan:     scan sr.get("tags", []) for r"S[1-6]"
    val = {... access path from walker B ...}
    if isinstance(val, str) and re.fullmatch(r"S[1-6]", val):
        return val
    return None


def get_business_advice(behavior_output: dict[str, Any]) -> list[str]:
    """Path discovered from baseline fixture inspection (Task 4.1, walker C).

    Always returns a list (empty if field absent or unexpected type).
    Each element normalized to str (some pipelines emit list[str], some list[dict]).
    """
    sr = behavior_output.get("structured_result", {})
    # Replace with actual path from walker C output, e.g.:
    #   raw = sr.get("evidence", {}).get("behavior_profile_narrative", {}).get("business_advice", [])
    raw = {... access path from walker C ...}
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            text = item.get("text") or item.get("content") or item.get("advice") or ""
            if text:
                out.append(str(text))
    return out
```

`re` 已在 runner.py 顶部 import（Task 1.2 已有）；如未 import，加 `import re`。

> **占位符纪律**：上述代码块内 `{... access path from walker X ...}` 是**显式标注的执行时填空**，必须在执行 Task 4.1 时由 walker 输出替换为真实代码。Plan 写作阶段不预填猜测路径——这是必改 #1 的核心要求。Plan 阶段不知道真路径，预填猜测会让 GREEN 假阳性通过。

**验证**：

```bash
python -c "
from tests.golden.runner import (
    load_fixture, get_churn_root_cause, get_recommended_segment, get_business_advice,
)
beh = load_fixture('behavior_profile', '824812551379353600')
comp = load_fixture('comprehensive_profile', '824812551379353600')
print('churn_root_cause:    ', get_churn_root_cause(beh))
print('recommended_segment: ', get_recommended_segment(comp))
print('business_advice len: ', len(get_business_advice(beh)))
"
```

预期：
- `recommended_segment` 必须是 `S1`-`S6` 之一（comprehensive smoke case 不能没 segment）
- `churn_root_cause` 可能为 None 或 list（取决于 G1 case 的实际特征）
- `business_advice len` ≥ 0（list 类型不抛异常即可）

如任一 helper 抛异常或取出非预期类型 → walker 输出与 helper 写法不一致，调整 helper（不调整 fixture）。

⛔ STOP — 报告 walker A/B/C 输出 + 三个 helper 实测取值，等 user 确认。

---

### Task 4.2 — TDD-RED：加 L2 字段断言

修改 `tests/test_golden_behavior_comprehensive.py`，把 behavior 测试改成：

```python
@pytest.mark.parametrize("case", _cases_for_skill("behavior_profile"), ids=lambda c: f"{c.case_id}-{c.uid}")
def test_behavior_fixture_loadable(case: GoldenCase, refresh_fixtures: bool) -> None:
    if refresh_fixtures:
        output = run_skill_real_llm("behavior_profile", case.uid)
        record_fixture("behavior_profile", case.uid, output)
        return
    output = load_fixture("behavior_profile", case.uid)
    assert "structured_result" in output, f"{case.case_id}: AgentOutput missing structured_result"
    assert_l1_structure("behavior_profile", output)
    assert_l2_fields(case, "behavior_profile", output)  # NEW
```

comprehensive 测试同样加 `assert_l2_fields(case, "comprehensive_profile", output)`。

import 顶部加 `assert_l2_fields`。

**验证**：

```bash
pytest tests/test_golden_behavior_comprehensive.py -v 2>&1 | tail -10
```

预期：5 个测试 FAILED 在 `NotImplementedError("Task 4.3")`。

⛔ STOP — 报告 RED 状态。

---

### Task 4.3 — TDD-GREEN：runner 实现 `assert_l2_fields`

修改 `tests/golden/runner.py`，替换 `assert_l2_fields` 的 `NotImplementedError`：

```python
CHURN_ROOT_CAUSE_ENUM = {
    "credit_limit_unmet",
    "interest_perception_high",
    "competitor_poaching",
    "ux_friction",
    "repayment_burden",
    "no_clear_signal",
}
SEGMENT_ENUM = {"S1", "S2", "S3", "S4", "S5", "S6"}


def assert_l2_fields(case: GoldenCase, skill: str, output: dict[str, Any]) -> None:
    """L2 — non-empty / enum / length checks."""
    sr = output["structured_result"]
    assert len(output.get("summary", "")) > 20, (
        f"L2[{skill}][{case.case_id}]: summary too short "
        f"(len={len(output.get('summary', ''))})"
    )
    assert len(output.get("report_markdown", "")) > 100, (
        f"L2[{skill}][{case.case_id}]: report_markdown too short "
        f"(len={len(output.get('report_markdown', ''))})"
    )

    if skill == "behavior_profile":
        beh_summary = get_behavior_summary(output)
        assert len(beh_summary) > 50, (
            f"L2[behavior][{case.case_id}]: behavior_summary too short (len={len(beh_summary)}); "
            f"actual='{beh_summary[:80]}'"
        )
        # churn_root_cause is conditional — only assert content if the field is present in fixture.
        # (Not all behavior cases must expose it; presence depends on prompt + decision rules.)
        # Cross-case coverage is enforced by test_l2_coverage_churn_root_cause (self-contained,
        # in the test file), not via shared module state — so this assertion is order-independent.
        rc = get_churn_root_cause(output)
        if rc is not None:
            assert isinstance(rc, list) and len(rc) > 0, (
                f"L2[behavior][{case.case_id}]: churn_root_cause present but empty list"
            )
            invalid = [v for v in rc if v not in CHURN_ROOT_CAUSE_ENUM]
            assert not invalid, (
                f"L2[behavior][{case.case_id}]: churn_root_cause has out-of-enum values={invalid}; "
                f"allowed={sorted(CHURN_ROOT_CAUSE_ENUM)}"
            )

    elif skill == "comprehensive_profile":
        seg = get_recommended_segment(output)
        assert seg is not None, (
            f"L2[comprehensive][{case.case_id}]: recommended_segment not found in fixture; "
            f"check tests/golden/runner.py:get_recommended_segment path"
        )
        assert seg in SEGMENT_ENUM, (
            f"L2[comprehensive][{case.case_id}]: segment={seg} not in {sorted(SEGMENT_ENUM)}"
        )
```

修改 `tests/test_golden_behavior_comprehensive.py`，文件末尾追加覆盖率守门测试（**自包含**：自己加载 fixture + 调 helper 统计，不依赖任何前置测试或共享模块状态，pytest -k / -p random / xdist 全兼容）：

```python
def test_l2_coverage_churn_root_cause(refresh_fixtures: bool) -> None:
    """At least 1 of the 4 behavior cases must expose churn_root_cause.

    Per-case L2 treats the field as conditional (not all cases must have it),
    but if NONE of 4 cases produce the field, the prompt has likely silently
    dropped the churn-attribution analysis — flag it loud.

    Self-contained: loads fixtures and queries the helper directly. Does NOT
    rely on shared module state or test execution order, so it's safe under
    pytest -k filtering, randomized order, and xdist parallelization.
    """
    if refresh_fixtures:
        pytest.skip("Coverage check not run during refresh")
    from tests.golden.runner import get_churn_root_cause
    behavior_cases = [c for c in GOLDEN_CASES if "behavior_profile" in c.skills]
    exposed = [
        c.case_id for c in behavior_cases
        if get_churn_root_cause(load_fixture("behavior_profile", c.uid)) is not None
    ]
    if not exposed:
        pytest.fail(
            f"L2 coverage failure: 0 of {len(behavior_cases)} behavior cases "
            f"({sorted(c.case_id for c in behavior_cases)}) exposed churn_root_cause. "
            f"Either prompt dropped the field, or get_churn_root_cause() path is wrong."
        )
```

import 顶部加 `assert_l2_fields`。

**验证**：

```bash
pytest tests/test_golden_behavior_comprehensive.py -v 2>&1 | tail -10
```

预期：5 个原测试 + 1 个 coverage = 6 个全 PASSED。

```bash
git add tests/golden/runner.py tests/test_golden_behavior_comprehensive.py
git commit -m "feat(eval): add L1+L2 layered assertions for golden tests"
```

⛔ STOP — 报告 Task 4.3 完成。

---

### Task 5.1 — TDD-RED：加 L3 单 case 反向断言

修改 `tests/test_golden_behavior_comprehensive.py`，behavior 测试再加一行：

```python
    assert_l3_content(case, output)  # NEW — only on behavior, not comprehensive
```

import 顶部加 `assert_l3_content`。

**验证**：4 个 behavior 测试 FAILED 在 `NotImplementedError("Task 5.2")`，1 个 comprehensive PASSED 不变。

⛔ STOP。

---

### Task 5.2 — TDD-GREEN：实现 L3 单 case 反向断言

修改 `tests/golden/runner.py`：

```python
# Forbidden patterns — sourced from docs/specs/golden-test-design.md §4 L3 table.
# Anchored at start of behavior_summary unless noted; advice pattern matches at start of each item.
# Reverse assertion logic: prompt regression is signaled by these templates appearing.
_L3A_FORBIDDEN_OPENING = re.compile(r"^该用户近\s*\d+\s*天活跃天数")
_L3B_FORBIDDEN_OPENING = re.compile(r"^标准化旅程共识别")
_L3C_FORBIDDEN_ADVICE = re.compile(r"^建议(优化|突出|触发|在关键流失窗口前)")


def assert_l3_content(case: GoldenCase, output: dict[str, Any]) -> None:
    """L3 — reverse-regex: forbidden template phrases must not appear."""
    summary = get_behavior_summary(output)

    if _L3A_FORBIDDEN_OPENING.search(summary):
        raise AssertionError(
            f"L3-a[{case.case_id}][uid={case.uid}]: behavior_summary matches forbidden opening "
            f"r'^该用户近\\s*\\d+\\s*天活跃天数'\n"
            f"  actual opening: {summary[:80]!r}\n"
            f"  selection_reason: {case.selection_reason}\n"
            f"  fixture: {fixture_path('behavior_profile', case.uid)}"
        )

    if _L3B_FORBIDDEN_OPENING.search(summary):
        raise AssertionError(
            f"L3-b[{case.case_id}][uid={case.uid}]: behavior_summary matches forbidden opening "
            f"r'^标准化旅程共识别'\n"
            f"  actual opening: {summary[:80]!r}\n"
            f"  fixture: {fixture_path('behavior_profile', case.uid)}"
        )

    # business_advice — read via helper (path discovered in Task 4.1, walker C);
    # always returns list[str] normalized.
    advice_list = get_business_advice(output)
    for i, text in enumerate(advice_list):
        if text and _L3C_FORBIDDEN_ADVICE.search(text):
            raise AssertionError(
                f"L3-c[{case.case_id}][uid={case.uid}]: business_advice[{i}] matches forbidden template "
                f"r'^建议(优化|突出|触发|在关键流失窗口前)'\n"
                f"  actual: {text[:80]!r}\n"
                f"  fixture: {fixture_path('behavior_profile', case.uid)}"
            )
```

**验证**：

```bash
pytest tests/test_golden_behavior_comprehensive.py -v 2>&1 | tail -10
```

预期：5 个测试全 PASSED。如果某个 fail —— **不要修 regex 让它过**，而是 STOP 报告"L3 真的捕捉到了 prompt 退化"，让 user 决定是改 prompt 还是承认这就是当前 baseline。

⛔ STOP。

---

### Task 5.3 — TDD-RED：加 L3-d 跨 case 断言

修改 `tests/test_golden_behavior_comprehensive.py`，文件末尾加：

```python
def test_l3d_quincena_diff_strong_vs_weak(refresh_fixtures: bool) -> None:
    """G1 (strong quincena, 70%) vs G3 (weak quincena, 36%) must diverge in payday narrative."""
    if refresh_fixtures:
        pytest.skip("Cross-case assertion not run during refresh")
    from tests.golden.runner import assert_l3d_quincena_diff
    g1 = load_fixture("behavior_profile", "824812551379353600")
    g3 = load_fixture("behavior_profile", "824848564055179264")
    assert_l3d_quincena_diff(g1, g3)
```

**验证**：1 个新测试 FAILED 在 `NotImplementedError("Task 5.4")`。

⛔ STOP。

---

### Task 5.4 — TDD-GREEN：实现 L3-d 跨 case quincena 差异化断言

修改 `tests/golden/runner.py`：

```python
_QUINCENA_KEYWORDS = ("quincena", "发薪", "月中", "月末", "15日", "30日", "1日", "工资日")


def _quincena_mentions(text: str) -> int:
    """Count occurrences of payday-related keywords in text (lowercased for uniform matching)."""
    lower = text.lower()
    return sum(lower.count(kw.lower()) for kw in _QUINCENA_KEYWORDS)


def assert_l3d_quincena_diff(strong_case_output: dict[str, Any], weak_case_output: dict[str, Any]) -> None:
    """Strong-quincena case (G1, 70%) must mention payday signals more than weak case (G3, 36%).

    Reverse assertion: prompt should NOT produce identical quincena narrative for both.
    """
    strong_summary = get_behavior_summary(strong_case_output)
    weak_summary = get_behavior_summary(weak_case_output)

    # 1) Full summaries must not be byte-identical (catches both opening collapse
    #    AND wholesale template reuse mid-paragraph)
    assert strong_summary != weak_summary, (
        f"L3-d: G1 (strong-quincena) and G3 (weak-quincena) behavior_summary are byte-identical "
        f"({len(strong_summary)} chars). Prompt is producing identical narrative for opposing signals."
    )

    # 2) Strong-quincena case must have strictly more payday mentions
    strong_mentions = _quincena_mentions(strong_summary)
    weak_mentions = _quincena_mentions(weak_summary)
    assert strong_mentions > weak_mentions, (
        f"L3-d: strong-quincena case (G1) must have MORE payday mentions than weak case (G3).\n"
        f"  G1 mentions={strong_mentions} | summary={strong_summary[:120]!r}\n"
        f"  G3 mentions={weak_mentions} | summary={weak_summary[:120]!r}\n"
        f"  This indicates the prompt is hallucinating payday narrative on weak signals, "
        f"OR collapsing the strong-signal case into a generic template."
    )
```

**验证**：

```bash
pytest tests/test_golden_behavior_comprehensive.py -v 2>&1 | tail -15
```

预期：所有 6 个测试 PASSED（5 单 case + 1 cross-case）。

```bash
git add tests/golden/runner.py tests/test_golden_behavior_comprehensive.py
git commit -m "feat(eval): add L3 reverse-regex + L3-d cross-case quincena diff assertions"
```

⛔ STOP — 报告 Task 5.4 完成。

---

### Task 6.1 — 全量回归确认

```bash
pytest tests/test_golden_behavior_comprehensive.py -v
pytest tests/ -v 2>&1 | tail -5
```

预期：
- 第一条：6 passed
- 第二条：原有所有测试（178+）零回归 + 6 个新测试 = 184+ passed

如果有任何 fail，STOP 不要继续，先排查。

---

### Task 6.2 — 更新 PLANNING.md / TASK.md + `[complete]` commit

1. `TASK.md` 在「已完成」节末尾追加（`{YYYY-MM-DD}` 替换为实际完成当日日期）：
   - `- [x] A1 Golden Test 评估框架（behavior 4 case + comprehensive 1 case smoke）— 完成（{YYYY-MM-DD}，docs/specs/golden-test-design.md + docs/plans/golden-test-plan.md）`
2. 如有「待做 / A1 Golden Test」条目，对应行打勾
3. `PLANNING.md` 末尾「更新记录」追加（同样 `{YYYY-MM-DD}` 用执行当日）：
   - `- [{YYYY-MM-DD}] A1 Golden Test 评估框架落地：tests/test_golden_behavior_comprehensive.py + tests/golden/runner.py + 5 个 fixture（4 behavior + 1 comprehensive smoke），三层断言 L1/L2/L3 + L3-d 跨 case quincena 差异化`

```bash
git add TASK.md PLANNING.md
git commit -m "[complete] golden-test-plan: evaluation framework

A1 Golden Test 落地：
- tests/test_golden_behavior_comprehensive.py（6 tests）
- tests/golden/runner.py（fixture I/O + L1/L2/L3 + L3-d）
- tests/fixtures/golden/{behavior_profile,comprehensive_profile}/ (5 fixtures)
- tests/conftest.py（--refresh-fixtures flag）"
```

**不 push**（CLAUDE.md：等 user 明确要求才 push）。

---

## 4. 风险与降级（Plan 阶段）

| 风险 | 触发 | 降级 |
|---|---|---|
| Task 3.2 baseline 录制时某 case `status != "ok"` | LLM 输出 fall back / data_missing | STOP，向 user 报告：要么换 UID，要么先修 prompt / 数据，再回到 Task 3.2 |
| Task 4.1 walker 找不到 `recommended_segment` | comprehensive 输出真没有 segment 字段 | STOP，向 user 报告：要么 L2 comprehensive 改成只校 status / persona 等已知字段，要么承认 comprehensive smoke 暂时不做 segment 断言 |
| Task 5.2 L3 反向断言一上来就 fail | baseline 本身就命中模板 = prompt 已退化 | STOP 报告，user 决定：(a) 修 prompt 重录 fixture (b) 调整禁用 regex (c) 接受当前 baseline |
| Task 5.4 L3-d strong > weak 不成立 | LLM 真的没区分两个 case | STOP 报告，user 决定（同上） |
| Task 3.2 中途 LLM API 失败 | 配额 / 鉴权 | STOP 报告，user 检查 .env + key.json 后重跑 |
| 某 fixture 文件超大（>200KB） | LLM 输出 report_markdown 巨长 | 接受，git 处理大文本 diff 没问题；如真离谱再加 trim 逻辑（本期不做） |
| LLM 非确定性导致重录 fixture 漂移（同 prompt 重录两次得到不同输出） | LLM 采样温度 / 模型版本变化 | 三层断言已吸收：L1/L2 校 schema 与枚举（不校具体值），L3 反向断言只锁"不能出现"模板（不锁具体措辞）；fixture diff 由 PR review 兜底。**但未来扩展 D 层（loose 比对 / 数值范围 / 跨次稳定性）时需重审本风险** |

---

## 5. 不在本期 Plan 内的事项（明确划分）

- 扩展 loose 断言层（D 模式）
- markdown 报告生成
- LLM-as-judge
- comprehensive 的多 case 覆盖（等数据补齐）
- 修正现有 prompt（Plan 只评估，不改 prompt）
- push 到远程

---

## 6. 更新记录

- [2026-05-01] 初始 Draft（Q6 数据扫描 + 4 UID 确认后产出）
- [2026-05-01] User 五点检查后修订 v2（10 处建议全部采纳）：
  - 必改 #1：Task 4.1 删除猜测路径预填，三个 helper 全部保留 NotImplementedError 直到 walker 跑完
  - 必改 #2：新增 `get_business_advice()` helper + walker C；Task 5.2 用 helper 替代硬编码
  - 必改 #3：新增 `_L2_CHURN_COVERED` set + `test_l2_coverage_churn_root_cause` 守门测试
  - 建议 #4：Task 1.1 / 1.2 / 2.2 / 3.2(fixture) / 4.3 / 5.4 各自独立 commit（共 6 个 feat commit）
  - 建议 #5：Task 3.2 fixture 审核脚本由 bash for-loop 改为单段 Python（PowerShell / bash 通用）
  - 建议 #6：§4 风险表新增 LLM 非确定性漂移条目
  - 优化 #7-#10：五点检查 #2 由 ⚠️ 改 ✅；Task 6.2 日期改"执行时填"；GOLDEN_CASES 注释 + L3 regex 来源注释回 design doc
- [2026-05-01] User v2 复审后修订 v3（3 处建议全部采纳）：
  - 必改 #1：删除 `_L2_CHURN_COVERED` 全局 set；`test_l2_coverage_churn_root_cause` 改为自包含（自己加载 4 个 fixture + 调 helper 统计 exposed），不依赖测试执行顺序，pytest -k / random / xdist 全兼容
  - 建议 #2：Task 5.4 `_quincena_mentions` 简化为单行 `sum(lower.count(kw.lower()) for kw in ...)`，删除 `if kw == "quincena"` 特殊分支
  - 建议 #3：Task 5.4 L3-d 断言 #1 由 `[:80]` 前缀比较改为完整 summary 比较（捕捉 opening collapse + 中段模板复用两种退化）
