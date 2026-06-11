# Plan 09 — Eval 体系（双国 50 条 NL→SQL + Rubric + LLM Judge + CI）

> **STATUS**: ✅ **READY-TO-EXECUTE — v3.2** （v3.2 三轮补 Task 0.1 requirements 依赖前置体检；2026-05-06 paranoid 五点复审补 country 合法性二阶门 + Task 1.4 量化 subset 选择规则；待用户最终复审后正式执行）
>
> **v3.2 二轮 paranoid 五点复审修订点**（2026-05-06）：
> - **P0-1 country 合法性二阶门**：`Task 3.1` 中 `_COUNTRY_MAP = {"mx": MEXICO, "th": THAILAND}` 仅在运行时遇非 mx/th case 抛 `ValueError`，但 50 条 fixture 在 Task 1.5 commit 前**没有 fail-fast 检查**。若数据分析师误标 `country: "id"` 进入 fixture，错误要拖到 Phase 4 跑 eval 才暴露。v3.2 Task 1.5 commit gate 加 `python` 一行校验：`country not in ('mx','th')` 直接 `exit 1`。
> - **P1 量化 subset 选择**：Task 1.4 v3.1 仅写「每个 category 选 1-2 条」，无法机械验证。v3.2 改为「5 category × 2 条 (mx + th 各 1) = 10 条」精确量化 + 校验脚本（`assert cats[(country, category)] <= 2`）。
>
> **v3.2 修订点**（对照 v3.1）：
> - **P3 高危**：v3.1 Task 0.1（baseline 体检）未对 `requirements.txt` 做依赖前置体检，CI 跑评测必备的 `sqlglot` / `pydantic` / `google-genai` 中任一缺失，会一直拖到 Phase 4 workflow 跑起来才暴露（白白浪费 ~2 小时调试）。v3.2 Task 0.1 加 `Select-String -Pattern "sqlglot|pydantic|google-genai|google-cloud"` 体检 + 缺包 `exit 1`，让缺包问题在 Phase 0 当场暴露。
>
> **v3 / v3.1 修订点**（对照 v2，保留供溯源）：
> - **致命-1**：`ModelClient` **没有 `generate(prompt, route_key=...)` 方法**，真实公开 API 是 `generate_structured(skill_name, prompt, fallback_result, response_schema=None, *, route_key=None) -> dict[str, Any]`。Task 0.2 smoke / Task 2.3 judge.py / Task 2.6 mock test 三处误用已全量重写。
> - **致命-2**：`generate_structured` 返回值不是 raw JSON string，而是 `{"status": "ok"|"model_unavailable", "structured_result": dict, "model_name": str, "prompt_preview": str}`。`run_judge` 需从 `result["structured_result"]` 取字典、判 `status` 判是否走 fallback。
> - **高危-1**：`run_actual_sql_gen` 未捕获 `OrchestratorError` / Pydantic `ValidationError`，一条 case 异常会终止整批跑。Task 3.1 已加 try/except。
> - **高危-2**：workflow `secrets.GCP_KEY_PATH` 实际传 JSON 内容不是路径。Task 4.1 已改为 `echo "$GCP_KEY_JSON" > $HOME/key.json + export GOOGLE_APPLICATION_CREDENTIALS=$HOME/key.json`。
> - **高危-3**：`_COUNTRY_MAP` 漏掉 id/pk/ph，遇不支持国家会 `KeyError`。Task 3.1 已改为 `dict.get + raise ValueError` 明确错误。
> - **中危**：重复 `### 0.3` 编号、`豆陈列` typo、Task 1.5 sqlglot dialect=`starrocks` 可能不被老版识别、缺 `MOCK_LLM=1` 提示，全量修复。
> - **v3.1 二轮**：Task 4.5 push gate 防失败 commit + Task 1.2 .jsonc note + Phase 2 commit calibration gate + Task 0.2 MOCK_LLM cleanup + Task 1.5 sqlglot None check + Task 4.3 timeout note + Task 2.4 cross-Plan coordination + Task 0.1 .reports dir。
>
> **作者**: Codex / Claude（自动生成草稿）
> **日期**: 2026-05-05（v2 修订 2026-05-05） / 2026-05-06（v3 / v3.1 / v3.2 修订）
> **关联 Spec**: `docs/specs/09-eval-system-design.md`（v3.2 同步修订）
> **HEAD baseline**: `bd05240`（Phase 0 commit 时以 `git rev-parse HEAD` 实际值为准，不依赖 Plan 07 / Plan 08）
> **预计 Phase 数**: 4

---

## 0. Baseline 共识

### 0.1 关联文档
- Spec: `docs/specs/09-eval-system-design.md`
- **现有 Golden Test 框架（本 Plan 复用）**：
  - `tests/golden/runner.py`
  - `tests/golden/judge_prompt.md`
  - `tests/golden/rubric.md`
  - `tests/golden/case_01_loyal_th_user.json` ~ `case_05_query_data_mx.json`（5 case）
  - `tests/fixtures/golden/{behavior_profile,comprehensive_profile}/`
- `Agent搭建实战学习笔记.md` Q8 Rubric 评估完整代码

### 0.1.1 Surgical Hard Boundary（本 Plan 不动下列文件）
| 不动 | 原因 |
|---|---|
| `data_acquisition_agent/` 整目录 | 仅 import 调用，绝不修改任何源文件 |
| `tests/golden/runner.py` | 现有运行器，复用不替换 |
| `tests/fixtures/golden/behavior_profile/` | 现有 4 case |
| `tests/fixtures/golden/comprehensive_profile/` | 现有 1 smoke case（注意 `_profile` 后缀）|
| `app/services/orchestrator_agent/` | 本 Plan 不涉及 |

### 0.2 设计原则
- **不新建 `tests/eval/` 目录**，避免与现有 `tests/golden/` 双轨；judge / rubric / calibration / run_eval / reports / baselines 全部走 `tests/golden/` 子目录
- fixture 走 `tests/fixtures/golden/sql_generation/`（与 behavior_profile/comprehensive_profile/ 并列）
- **复用 `tests/golden/runner.py`**（Phase 3 CLI 内部调用，只补 NL→SQL 场景入口）
- **`config.yaml` 路由全部走 `gemini` provider 名**（不新增 gemini_pro / gemini_flash，避免名字混乱）
- **路由只用平铺 `key: provider_name` 格式**（与现有 9 条路由一致），**不使用** `{primary, fallback_chain}` 嵌套结构
- **LLM 调用一律走 `app/core/model_client.py::ModelClient`**（CLAUDE.md Zero Tolerance 第 5 条），禁止直接 `import google-genai`

### 0.3 baseline commit
```bash
git commit --allow-empty -m "[baseline] plan-09 — before execution"
```

### 0.4 测试矩阵
- 单元：rubric / judge / cli
- Calibration：人工 vs LLM 偏差 < 1.0
- CI：PR subset 触发跑通

---

## 1. 范围

### 1.1 ✅ 包含
- 50 条评测集（mx 25 + th 25）+ expected_sqls
- 10 条 PR subset
- Rubric 5 维定义
- LLM Judge（`gemini` provider 下的 gemini-2.5-flash）+ Pydantic
- Calibration 校准脚本（`CALIBRATION_HUMAN_SCORES` 本 Plan 必须实际填 5-10 条，不允许空列表 ship）
- CLI: `python -m tests.golden.run_eval`
- Baseline 对比 + Markdown 报告（V1 即出 delta，对应 Spec §5.2）
- GitHub Actions workflow（PR + 夜间）

### 1.2 ❌ 不包含
- run_profile / run_trace 等非 SQL 工具评测
- 自动调 prompt 优化
- 跨模型对比

### 1.3 依赖前置与降级路径（2026-05-05 补）

> 本 Plan **不能独立一次跳完**。Phase 启动前必须对齐 3 个外部依赖：

| # | 依赖项 | 依赖者 | 未就绪时的降级路径 |
|---|---|---|---|
| **D1** | 50 条 NL→SQL 评测集（mx 25 + th 25） | Phase 1 Task 1.2/1.3 | **默认采纳分阶段策略**：先收集 mx 25 条 → 完整跳完 Phase 1–4（mx-only baseline）→ th 25 条就绪后补 commit 扩到双国 50 条。该降级不影响 CI workflow / Rubric / Judge 任何一个代码路径，仅 Phase 4 评测报告临时仅含 mx 列。 |
| **D2** | Plan 08 (`JudgedDataAcquisitionOrchestrator` wrapper) 已合主线 | Phase 4 Task 4.x “baseline vs branch delta” | **wrapper 未落地时**：`build_report` 读 `baselines/main_latest.json` 返回 None → 报告仅显示本次分（无 delta 列）。Phase 4 Task 4.1 workflow 正常跳过 baseline diff 比对，nightly cron 首跑后自然生成 baseline。**不阻塞 Plan 09 独立 Phase 4 commit。** |
| **D3** | `CALIBRATION_HUMAN_SCORES` 5–10 条人工打分 | Phase 2 Task 2.5 commit gate | **不允许空 ship**。责任人 = 数据分析师 A，时间表 = Phase 2 启动前 **T-2 天**交出 5–10 条人工评分（以 Plan 09 baseline commit 当日为 T-0）。按 Spec §2.4 双人审核 + commit message 实名签字。未在期限交付 → Phase 2 commit gate 拒绝（`assert len(CALIBRATION_HUMAN_SCORES) >= 5`）→ Plan 09 暂停。 |

> **启动节奏推荐**：
> - 阶段 1：Phase 0 + Phase 2 Task 2.1–2.4（仅依赖 D3）— 可独立开启
> - 阶段 2：Phase 1（依赖 D1 mx 25 条就绪）
> - 阶段 3：Phase 3–4（依赖 D2/Plan 08 未落地 → 走 D2 降级路径）
> - **上述三阶段可与 Plan 08 并行，不互锁**。

---

## Phase 0 — Baseline 核对

### Task 0.1 摸清 tests/golden 与 .github/workflows 实际状态
```powershell
New-Item -ItemType Directory -Path .reports -Force | Out-Null   # v3.1 补：避免后续仿中报告写入失败
Write-Host "=== tests/golden/ ==="
Get-ChildItem tests/golden/ -Recurse | Select-Object FullName
Write-Host "`n=== tests/fixtures/golden/ ==="
Get-ChildItem tests/fixtures/golden/ -Recurse | Select-Object FullName
Write-Host "`n=== .github/workflows/ ==="
if (Test-Path .github/workflows/) { Get-ChildItem .github/workflows/ } else { Write-Host "[NOT EXIST — Phase 4 Task 4.1 会创建]" }
Write-Host "`n=== HEAD ==="
git rev-parse HEAD

# v3.2 补：依赖前置体检（CI 跑评测必备 4 个包，缺任一直接 abort 不进 Phase 1）
Write-Host "`n=== requirements.txt 关键依赖 ==="
$deps = Select-String -Path requirements.txt -Pattern "sqlglot|pydantic|google-genai|google-cloud" |
        Select-Object -ExpandProperty Line
$deps
$missing = @("sqlglot", "pydantic", "google-genai") | Where-Object {
    -not ($deps -join "`n").ToLower().Contains($_.ToLower())
}
if ($missing.Count -gt 0) {
    Write-Host "[ABORT] requirements.txt 缺依赖：$($missing -join ', ') — 先补再进 Phase 1" -ForegroundColor Red
    exit 1
}
```
**记录**：实际文件清单写入 `.reports/plan-09-phase0.txt`。**预期**：`.github/workflows/` 不存在，`tests/fixtures/golden/comprehensive_profile/` 带 `_profile` 后缀，`requirements.txt` 已有 `sqlglot` / `pydantic` / `google-genai`。

### Task 0.2 验证 ModelClient 可调走现有 `gemini` route
```python
# 临时跑：
#   $env:MOCK_LLM="1"   # PowerShell：MOCK 模式免 GCP 凭据；生产路径记得 unset
#   python -c "<以下脚本>"
from app.core.model_client import ModelClient
client = ModelClient()
result = client.generate_structured(
    skill_name="eval_smoke",
    prompt="return JSON {\"hello\": \"world\"}",
    fallback_result={"hello": "fallback"},
    response_schema={
        "type": "object",
        "properties": {"hello": {"type": "string"}},
        "required": ["hello"],
    },
    route_key="orchestrator_agent.decide",
)
print(result)
```
**预期**：`result["status"] == "ok"` 且 `result["structured_result"]["hello"]` 返回非空字串（mock 模式下为 `"fallback"`，生产下为模型生成值）。**注意**：`route_key` 必须与 `config.yaml::llm.routes` 中现有键严格一致（现有是 `orchestrator_agent.decide`，**不是** `orchestrator_agent`）。
> v3.1 补：smoke 跑完后务必 `Remove-Item Env:\MOCK_LLM` 清理环境变量，避免后续 Phase 1-3 默默跑在 mock 下、无真实 LLM 验证：
> ```powershell
> Remove-Item Env:\MOCK_LLM -ErrorAction SilentlyContinue
> ```
>
> **为什么不用 `client.generate("hello", route_key=...)` ？** 因为 `ModelClient` **没有 `generate()` 方法**，唯一公开 LLM 调用入口就是 `generate_structured(...)`（v2 误写为 `generate`，v3 修复）。

### Task 0.3 创建评测子目录（全部在 tests/golden 下，**不创建 tests/eval**）
```powershell
New-Item -ItemType Directory -Path `
  tests/golden/reports, `
  tests/golden/baselines/main_history, `
  tests/fixtures/golden/sql_generation/expected_sqls/mx, `
  tests/fixtures/golden/sql_generation/expected_sqls/th `
  -Force
# 占位以让 git 跟踪
New-Item -ItemType File -Path `
  tests/golden/reports/.gitkeep, `
  tests/golden/baselines/main_history/.gitkeep, `
  tests/fixtures/golden/sql_generation/expected_sqls/mx/.gitkeep, `
  tests/fixtures/golden/sql_generation/expected_sqls/th/.gitkeep `
  -Force
```

### Phase 0 commit
```powershell
git add tests/golden/reports tests/golden/baselines tests/fixtures/golden/sql_generation
git commit --allow-empty -m "chore(09): phase 0 baseline + sql_generation skeleton"
```

---

## Phase 1 — 评测集就位

### Task 1.1 准备 50 条 NL → expected SQL
**责任人**: 数据分析师 A（代表性筛选）+ B（交叉审核）。
**「代表性」判定标准**（本 Plan 事先明确，避免「凭感觉」）：
1. 5 类难度（simple_query / aggregation / join / time_window / edge_case）每类 ≥ 5 条/国
2. 来源覆盖：实际线上需求（da-agent 历史 request_id 日志）≥ 60%，LLM 生成补足 ≤ 40%
3. 长度：P50 ∈ [20, 100] 字符，P95 ≤ 300
4. 语言：mx 全西/中混，th 全英/中混
5. 不重复：文本余弦相似度 < 0.85（sentence-transformers 粗滤）

**手动步骤**:
1. 数据分析师 A 按上述 5 条标准从历史日志/真实需求中筛选 50 条代表性 NL query（mx 25 + th 25）
2. 按难度分布：simple_query 5 / aggregation 5 / join 5 / time_window 5 / edge_case 5（每国）
3. 用 LLM（gemini-2.5-flash via ModelClient）生成 expected SQL → 数据分析师 B 人工审核修正

> ⚠️ **STOP 条件**：用户没准备好 50 条原始数据 → 可以先做 mx 25 条，th 25 条留到下一轮（Plan 可部分验收，补完后重跑 Phase 4 Task 4.3）。

### Task 1.2 写 eval_set.json
**Create**: `tests/fixtures/golden/sql_generation/eval_set.json`
**示例**（v3.1：**仅为说明片段**、**落盘前必须删除中文注释**，JSON 不支持 `//`）：
```jsonc
[
  {
    "case_id": "mx_001",
    "country": "mx",
    "category": "simple_query",
    "difficulty": "easy",
    "nl_query": "查询用户 824812551379353600 的最近一次登录时间",
    "expected_sql_path": "expected_sqls/mx/case_001.sql",
    "tags": ["user_lookup", "timestamp"],
    "notes": "基础场景"
  }
]
```
> **说明**：上面为 `.jsonc` 示意位。实际落盘为纯 JSON、完整 50 条，不能有任何注释。
> **验证命令**：`python -c "import json; json.load(open('tests/fixtures/golden/sql_generation/eval_set.json', encoding='utf-8'))"` 必须无错。
> **路径说明**：`expected_sql_path` 为相对于 `tests/fixtures/golden/sql_generation/` 的路径。CLI 加载时走 `tests/fixtures/golden/sql_generation/<expected_sql_path>`。

### Task 1.3 写 expected_sqls/{mx,th}/case_*.sql 共 50 个文件
**Create**: 50 个 .sql 文件，路径 `tests/fixtures/golden/sql_generation/expected_sqls/{mx,th}/case_NNN.sql`。
**命名规则**（v3 明确）：每国编号 `case_001.sql` → `case_025.sql`（三位零填充），mx / th 并列不交叉；与 `eval_set.json::case_id` 后缀编号一致（例 mx_001 ↔ mx/case_001.sql）。
**示例**:
```sql
-- tests/fixtures/golden/sql_generation/expected_sqls/mx/case_001.sql
SELECT user_id, MAX(login_time) AS last_login
FROM dwd_user_logins
WHERE user_id = 824812551379353600
GROUP BY user_id;
```

### Task 1.4 写 eval_subset.json（PR 用，10 条）
**Create**: `tests/fixtures/golden/sql_generation/eval_subset.json`
**选择规则**（5 category × 2 条（mx + th 各 1） = 10 条）：
- `simple_query`：1 mx + 1 th
- `aggregation`：1 mx + 1 th
- `join`：1 mx + 1 th
- `time_window`：1 mx + 1 th
- `edge_case`：1 mx + 1 th

**验证命令**：
```powershell
python -c "
import json
subset = json.load(open('tests/fixtures/golden/sql_generation/eval_subset.json', encoding='utf-8'))
assert len(subset) == 10, f'subset size {len(subset)} != 10'
cats = {}
for c in subset:
    key = (c['country'], c['category'])
    cats[key] = cats.get(key, 0) + 1
    assert cats[key] <= 2, f'category {key} 出现 {cats[key]} 次 > 2'
print(f'OK: 10 条 subset，category 分布正确')
"
```
**预期**：`OK: 10 条 subset，category 分布正确`

### Task 1.5 双人审 expected SQL
**责任人**: 数据分析师 A（Task 1.1 筛选人）+ 数据分析师 B（不同人，交叉审核）。
**手动步骤**:
1. A 和 B 各自独立审核 50 条 expected SQL，确认逻辑正确
2. 分歧 case 由项目负责人裁决
3. 审完后 A 在 commit message 注明 "reviewed-by: A, B"
**验证命令**（机械检查）：
```powershell
# v3.2 补：P0-1 country 合法性门——eval_set.json 中 country 必须仅含 "mx" / "th"（V1 限定）
python -c "
import json
data = json.load(open('tests/fixtures/golden/sql_generation/eval_set.json', encoding='utf-8'))
invalid = [c for c in data if c['country'] not in ('mx', 'th')]
if invalid:
    print(f'ERROR: {len(invalid)} case 含非法 country 值：{[c[\"case_id\"] for c in invalid]}')
    raise SystemExit(1)
print(f'OK: 所有 {len(data)} case country 值合法（V1 仅受 mx + th）')
"
```
**预期**：`OK: 所有 50 case country 值合法（V1 仅受 mx + th）`。如出现非法值，说明 Task 1.1 筛选阶段闯进了 V1 不支持的国家，必须回 Task 1.1 从语料里删。

```powershell
# 所有 expected_sql 文件能被 sqlglot parse、且返回非空 AST
python -c "
import sqlglot, glob
for f in glob.glob('tests/fixtures/golden/sql_generation/expected_sqls/**/*.sql', recursive=True):
    try:
        result = sqlglot.parse(open(f, encoding='utf-8').read(), read='mysql')
    except Exception as e:
        print(f'PARSE FAIL: {f} — {e}')
        raise
    if not result or all(s is None for s in result):
        # v3.1：老版本 sqlglot 遇错误 SQL 有时返 [None] 不抛，补上这道门
        print(f'PARSE EMPTY: {f}')
        raise SystemExit(1)
print('all parsed OK')
"
```
**预期**：输出 `all parsed OK`。
> **dialect 说明**（v3）：`read='mysql'` 是保守选择——StarRocks 兼容 MySQL 协议且语法近 95% 重叠；sqlglot 0.x 老版未必识别 `starrocks` 字面量，选 mysql 可避免 `dialect_not_found` 误报。若项目 sqlglot 版本≥1.0 且需严格验证 StarRocks 特性，可后续改 `read='starrocks'`。

### Phase 1 commit
```powershell
git add tests/fixtures/golden/sql_generation/
git commit -m "feat(09): phase 1 eval set 50 cases (mx 25 + th 25, reviewed-by: A, B)"
```

---

## Phase 2 — Rubric + Judge + Calibration

### Task 2.1 实现 Rubric 定义
**Create**: `tests/golden/rubric.py`（`tests/golden/__init__.py` 已存在于 Phase 0 核对，**不重复创建**）
**完整代码**:
```python
"""Rubric 5-dimensional definitions (Plan 09 Phase 2)."""

RUBRIC_DIMENSIONS = {
    "syntax": {
        "5": "SQL 完全符合 StarRocks 语法，sqlglot parse 无错，字段名全在 schema 中",
        "4": "语法正确，但有 1 个字段名拼写错误或边角问题",
        "3": "语法正确，但有 2-3 个字段问题",
        "2": "基本正确，需明显修改才能跑通",
        "1": "语法错误，无法 parse",
    },
    "semantics": {
        "5": "执行结果与 expected SQL 完全一致",
        "4": "结果基本一致，仅排序/边界差异",
        "3": "查询逻辑接近，部分场景结果不同",
        "2": "查询逻辑偏离较多",
        "1": "完全不同的查询逻辑",
    },
    "performance": {
        "5": "走索引、JOIN ≤ 3、有 LIMIT、无嵌套子查询",
        "4": "性能可接受，1 个小问题",
        "3": "2-3 个性能问题",
        "2": "性能差",
        "1": "全表扫 / 嵌套深度 > 3 / JOIN > 5",
    },
    "security": {
        "5": "符合脱敏，无 DDL，无敏感字段暴露",
        "4": "1 个轻微敏感字段但场景合理",
        "3": "可能有问题需 review",
        "2": "暴露了 1 个敏感字段",
        "1": "含 DDL 或多个敏感字段暴露",
    },
    "readability": {
        "5": "格式规范、缩进合理、有意义的别名、必要注释",
        "4": "格式良好，1 个小问题",
        "3": "可读性一般",
        "2": "格式混乱",
        "1": "无法快速理解逻辑",
    },
}


def format_rubric_for_prompt() -> str:
    out = []
    for dim, levels in RUBRIC_DIMENSIONS.items():
        out.append(f"### {dim}")
        for score, desc in levels.items():
            out.append(f"  {score}: {desc}")
    return "\n".join(out)
```

### Task 2.2 实现 Judge 输出 schema
**Create**: `tests/golden/schemas.py`
**完整代码**:
```python
"""Pydantic output schema for Rubric Judge (Plan 09 Phase 2)."""
from pydantic import BaseModel
from typing import Literal


class RubricScores(BaseModel):
    syntax: int
    semantics: int
    performance: int
    security: int
    readability: int


class JudgeResult(BaseModel):
    scores: RubricScores
    reasoning: dict[str, str]
    overall: float
    verdict: Literal["pass", "fail", "review"]
```

### Task 2.3 实现 LLM Judge（走 `ModelClient.generate_structured`，错误可逆）
**Create**: `tests/golden/judge.py`
**关键修订**（对照 v2）：v2 误写 `client.generate(prompt, route_key=...)`——`ModelClient` **不存在此方法**。唯一公开 LLM 调用 API 是 `generate_structured(skill_name, prompt, fallback_result, response_schema=None, *, route_key=None) -> dict[str, Any]`，返回值为 `{"status": "ok"|"model_unavailable", "structured_result": dict, "model_name": str, "prompt_preview": str}`。

**完整代码**:
```python
"""LLM-as-Judge for SQL eval (Plan 09 Phase 2). 统一走 ModelClient.generate_structured，路由 eval.judge → gemini.

v3 修复：`generate_structured` 返回 dict，需从 structured_result 取数据 + 判 status。
"""
from typing import Any

from app.core.model_client import ModelClient

from .rubric import format_rubric_for_prompt
from .schemas import JudgeResult, RubricScores


JUDGE_PROMPT = """你是一个 SQL 评测专家。请按以下 Rubric 对 actual SQL 打分。

## 评测案例
- NL Query: {nl_query}
- Country: {country}
- Category: {category}

## Expected SQL
```sql
{expected_sql}
```

## Actual SQL
```sql
{actual_sql}
```

## 评分标准（每维 1-5 分）
{rubric}

## 输出严格 JSON
{{
  "scores": {{
    "syntax": 1-5, "semantics": 1-5, "performance": 1-5,
    "security": 1-5, "readability": 1-5
  }},
  "reasoning": {{
    "syntax": "...", "semantics": "...", "performance": "...",
    "security": "...", "readability": "..."
  }},
  "overall": 1-5平均分,
  "verdict": "pass" | "fail" | "review"
}}
"""


_JUDGE_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "object",
            "properties": {
                "syntax": {"type": "integer"},
                "semantics": {"type": "integer"},
                "performance": {"type": "integer"},
                "security": {"type": "integer"},
                "readability": {"type": "integer"},
            },
            "required": ["syntax", "semantics", "performance", "security", "readability"],
        },
        "reasoning": {"type": "object"},
        "overall": {"type": "number"},
        "verdict": {"type": "string", "enum": ["pass", "fail", "review"]},
    },
    "required": ["scores", "reasoning", "overall", "verdict"],
}


_FALLBACK_REVIEW: dict[str, Any] = {
    "scores": {"syntax": 1, "semantics": 1, "performance": 1, "security": 1, "readability": 1},
    "reasoning": {dim: "model_unavailable" for dim in ("syntax", "semantics", "performance", "security", "readability")},
    "overall": 1.0,
    "verdict": "review",
}


def run_judge(case: dict, actual_sql: str, expected_sql: str,
              client: ModelClient | None = None) -> JudgeResult:
    client = client or ModelClient()
    prompt = JUDGE_PROMPT.format(
        nl_query=case["nl_query"],
        country=case["country"],
        category=case["category"],
        expected_sql=expected_sql,
        actual_sql=actual_sql,
        rubric=format_rubric_for_prompt(),
    )
    result = client.generate_structured(
        skill_name="eval_judge",
        prompt=prompt,
        fallback_result=_FALLBACK_REVIEW,
        response_schema=_JUDGE_RESPONSE_SCHEMA,
        route_key="eval.judge",
    )
    payload = result.get("structured_result", _FALLBACK_REVIEW)
    # status=="model_unavailable" 时 payload 已是 fallback；status=="ok" 时 payload 是模型输出 dict。
    return JudgeResult(
        scores=RubricScores(**payload["scores"]),
        reasoning=payload["reasoning"],
        overall=float(payload["overall"]),
        verdict=payload["verdict"],
    )
```

### Task 2.4 config.yaml 添加 eval.judge 路由（平铺格式）
**Modify**: `config.yaml`。**表明**：现有 9 条路由都用平铺 `key: provider_name` 格式（如 `app_profile.explainer: gemini`），本 Plan **不使用** `{primary, fallback_chain}` 嵌套结构，避免与现有 schema 冲突。

> **v3.1 跨 Plan 协调**：Plan 10 Task 2.4 也修改同一处 `config.yaml`。两 Plan 串行跑时，仅首个 Plan 的 oldString 有效；执行人需按下面顺序的什么顺序在跑、选对应分支：
> - **如本 Plan 首跑**（当前 `config.yaml` 末尾仅含 `orchestrator_agent.decide: gemini` + `default_provider`）：使用下面 oldString/newString。
> - **如 Plan 10 已先跑**（`memory.summarizer` 已在）：oldString 改为包含 `memory.summarizer: gemini` 的实际末尾两行，newString 在其后补 `eval.judge: gemini`。

**oldString**（现有最后一行 routes）：
```yaml
    orchestrator_agent.decide: gemini
  default_provider: gemini
```
**newString**：
```yaml
    orchestrator_agent.decide: gemini
    eval.judge: gemini   # Plan 09 Phase 2 — LLM-as-Judge for NL→SQL eval
  default_provider: gemini
```

### Task 2.5 实现 Calibration 脚本 + 填充人工分数
**Create**: `tests/golden/calibration.py`
**责任人**: 数据分析师 A（Task 1.1 同人）主负责填入 5-10 条人工分数。
**完整代码**:
```python
"""LLM Judge calibration vs human (Plan 09 Phase 2).人工分本 Plan 必须填，不允许空列表 ship."""
import json
from pathlib import Path
from .judge import run_judge


# === Phase 2 Task 2.5 责任人必填：5-10 条人工打分作为校准基准 ===
# 示例格式严格保持，key 不可变
CALIBRATION_HUMAN_SCORES: list[dict] = [
    # {
    #     "case_id": "mx_001",
    #     "actual_sql": "SELECT user_id, MAX(login_time) AS last_login FROM dwd_user_logins WHERE user_id=824812551379353600 GROUP BY user_id;",
    #     "human_scores": {"syntax": 5, "semantics": 5, "performance": 5, "security": 5, "readability": 4},
    # },
    # … 5-10 条（责任人在 Phase 2 实际填入）
]


def calibrate(client=None) -> float:
    """返回平均偏差。> 1.0 调 rubric；> 2.0 回退."""
    if not CALIBRATION_HUMAN_SCORES:
        raise RuntimeError(
            "CALIBRATION_HUMAN_SCORES 为空。Phase 2 Task 2.5 未完成，不允许 ship."
        )

    eval_set = json.loads(
        Path("tests/fixtures/golden/sql_generation/eval_set.json").read_text(encoding="utf-8")
    )
    cases_by_id = {c["case_id"]: c for c in eval_set}

    diffs: list[float] = []
    for entry in CALIBRATION_HUMAN_SCORES:
        case = cases_by_id[entry["case_id"]]
        expected = Path(
            f"tests/fixtures/golden/sql_generation/{case['expected_sql_path']}"
        ).read_text(encoding="utf-8")
        result = run_judge(case, entry["actual_sql"], expected, client)
        for dim, human_score in entry["human_scores"].items():
            llm_score = getattr(result.scores, dim)
            diffs.append(abs(llm_score - human_score))

    return sum(diffs) / len(diffs) if diffs else 0.0
```

### Task 2.6 unit test
**Create**: `tests/golden/test_judge.py`（走 mock，不调真实 LLM）
**v3 修订**：从 mock `client.generate.return_value = json.dumps(...)` 改为 mock `client.generate_structured.return_value = {"status": "ok", "structured_result": {...}, ...}`——与 Task 2.3 重写后的 `run_judge` 实际调用保持一致。
**完整代码**:
```python
from unittest.mock import MagicMock

from tests.golden.judge import run_judge


def test_judge_returns_structured_result():
    mock_client = MagicMock()
    mock_client.generate_structured.return_value = {
        "status": "ok",
        "structured_result": {
            "scores": {
                "syntax": 5, "semantics": 5, "performance": 4,
                "security": 5, "readability": 4,
            },
            "reasoning": {
                "syntax": "ok", "semantics": "ok", "performance": "ok",
                "security": "ok", "readability": "ok",
            },
            "overall": 4.6,
            "verdict": "pass",
        },
        "model_name": "gemini-2.5-flash",
        "prompt_preview": "你是...",
    }
    case = {"nl_query": "test", "country": "mx", "category": "simple_query"}
    result = run_judge(case, "SELECT 1", "SELECT 1", client=mock_client)
    assert result.verdict == "pass"
    assert result.scores.syntax == 5
    assert result.overall == 4.6


def test_judge_handles_model_unavailable_via_fallback():
    """模型不可用时 generate_structured 返 fallback_result（v3 新增）。"""
    mock_client = MagicMock()
    mock_client.generate_structured.return_value = {
        "status": "model_unavailable",
        "structured_result": {
            "scores": {
                "syntax": 1, "semantics": 1, "performance": 1,
                "security": 1, "readability": 1,
            },
            "reasoning": {
                "syntax": "model_unavailable", "semantics": "model_unavailable",
                "performance": "model_unavailable", "security": "model_unavailable",
                "readability": "model_unavailable",
            },
            "overall": 1.0,
            "verdict": "review",
            "status": "model_unavailable",
            "model_error": "timeout",
        },
        "model_name": "gemini-2.5-flash",
        "prompt_preview": "",
    }
    case = {"nl_query": "test", "country": "mx", "category": "simple_query"}
    result = run_judge(case, "", "SELECT 1", client=mock_client)
    assert result.verdict == "review"
    assert result.overall == 1.0
```

### Phase 2 commit
```powershell
# v3.1 补：Phase 2 commit 门、`CALIBRATION_HUMAN_SCORES` 未填则拒绝 commit
python -c "from tests.golden.calibration import CALIBRATION_HUMAN_SCORES; assert len(CALIBRATION_HUMAN_SCORES) >= 5, 'Task 2.5 未填 5-10 条人工分，不允许 commit'"
if ($LASTEXITCODE -ne 0) { exit 1 }

git add tests/golden/rubric.py tests/golden/schemas.py tests/golden/judge.py tests/golden/calibration.py tests/golden/test_judge.py config.yaml
git commit -m "feat(09): phase 2 rubric + LLM judge + calibration (eval.judge route)"
```

---

## Phase 3 — CLI + Baseline 对比

### Task 3.1 实现 CLI（复用 tests/golden/runner.py 思路，调用 da-agent 公开类 API）
**Create**: `tests/golden/run_eval.py`
**关键修复**：`data_acquisition_agent` **不导出模块级 `generate_sql()` 函数**，只有类 `DataAcquisitionOrchestrator.generate(GenerateRequest) → GenerateResponse`。
**完整代码**:
```python
"""CLI: python -m tests.golden.run_eval (Plan 09 Phase 3).

复用思路：Actual SQL 来自现有 DataAcquisitionOrchestrator.generate()（不修改 da-agent）。
baseline diff：读 baselines/main_latest.json 与本次跑分逐 case 准备 delta（V1 即出）。
"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from data_acquisition_agent.orchestrator import (
    DataAcquisitionOrchestrator,
    OrchestratorError,
)
from data_acquisition_agent.schemas import GenerateRequest, TargetCountry
from pydantic import ValidationError

from .judge import run_judge


FIXTURE_DIR = Path("tests/fixtures/golden/sql_generation")
REPORT_DIR = Path("tests/golden/reports")
BASELINE_DIR = Path("tests/golden/baselines")

# country code (mx/th) → da-agent TargetCountry enum。id/pk/ph 为 V2 补充。
_COUNTRY_MAP = {
    "mx": TargetCountry.MEXICO,
    "th": TargetCountry.THAILAND,
}


def load_eval_set(subset: bool = False) -> list[dict]:
    fname = "eval_subset.json" if subset else "eval_set.json"
    return json.loads((FIXTURE_DIR / fname).read_text(encoding="utf-8"))


def run_actual_sql_gen(case: dict, orch: DataAcquisitionOrchestrator) -> str:
    """调用现有 da-agent 生成 SQL（不修改 da-agent）；v3 加入异常容错。

    三类可预期异常转为空 SQL，交 Judge 评 1 分；不让一条 case 拖垄整批跑：
    1. `KeyError` — case["country"] 不在 _COUNTRY_MAP（转为 ValueError，错误位置明确）
    2. `OrchestratorError` — da-agent 请求本身被拒（credential leak / DDL policy / prompt too large）
    3. `ValidationError` — LLM 返回违反 Pydantic schema（如 sql、python 同时为空）
    """
    country_code = case.get("country")
    target_country = _COUNTRY_MAP.get(country_code)
    if target_country is None:
        # eval_set.json 这一条记录本身不合法；v1 仅支持 mx/th。
        raise ValueError(
            f"unsupported country={country_code!r} for case_id={case.get('case_id')!r}; "
            f"V1 supports {sorted(_COUNTRY_MAP.keys())}"
        )
    req = GenerateRequest(
        natural_language_request=case["nl_query"],
        target_country=target_country,
    )
    try:
        resp = orch.generate(req)
    except (OrchestratorError, ValidationError) as exc:
        # 交上层：actual_sql="" 走 Judge， verdict 必为 fail/review。
        return ""
    return resp.sql or ""


def build_report(results: list[dict], duration: float, baseline: str | None,
                 baseline_results: list[dict] | None) -> str:
    dims = ["syntax", "semantics", "performance", "security", "readability"]
    avg = {d: sum(r["judge"]["scores"][d] for r in results) / len(results) for d in dims}
    overall_avg = sum(avg.values()) / len(avg)
    pass_count = sum(1 for r in results if r["judge"]["verdict"] == "pass")

    lines = [
        f"# Eval Report — {datetime.now().isoformat()}",
        "",
        f"- Total cases: {len(results)}",
        f"- Duration: {duration:.1f} s",
        f"- Baseline: {baseline or '（未指定）'}",
        "",
        "## 总体分数",
        "",
        "| 维度 | Branch | Baseline | Δ |",
        "|---|---|---|---|",
    ]
    if baseline_results:
        base_avg = {d: sum(r["judge"]["scores"][d] for r in baseline_results) / len(baseline_results) for d in dims}
        for d in dims:
            delta = avg[d] - base_avg[d]
            sign = "+" if delta >= 0 else ""
            mark = "✅" if delta > 0.05 else ("⚠️" if delta < -0.05 else "")
            lines.append(f"| {d} | {avg[d]:.2f} | {base_avg[d]:.2f} | {sign}{delta:.2f} {mark} |")
        base_overall = sum(base_avg.values()) / len(base_avg)
        d_overall = overall_avg - base_overall
        lines.append(f"| **overall** | **{overall_avg:.2f}** | **{base_overall:.2f}** | **{('+' if d_overall>=0 else '')}{d_overall:.2f}** |")
    else:
        for d in dims:
            lines.append(f"| {d} | {avg[d]:.2f} | — | — |")
        lines.append(f"| **overall** | **{overall_avg:.2f}** | — | — |")

    lines += ["", f"## 通过率\n\n{pass_count}/{len(results)} ({100*pass_count//len(results)}%)"]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subset", action="store_true")
    parser.add_argument("--country", choices=["mx", "th"], default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--baseline", default=None, help="对比基线分支名。读 baselines/main_latest.json")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    args = parser.parse_args()

    cases = load_eval_set(subset=args.subset)
    if args.country:
        cases = [c for c in cases if c["country"] == args.country]
    if args.limit:
        cases = cases[: args.limit]

    orch = DataAcquisitionOrchestrator()
    results: list[dict] = []
    start = time.time()
    for case in cases:
        actual_sql = run_actual_sql_gen(case, orch)
        expected_sql = (FIXTURE_DIR / case["expected_sql_path"]).read_text(encoding="utf-8")
        judge_result = run_judge(case, actual_sql, expected_sql)
        results.append({
            "case_id": case["case_id"],
            "actual_sql": actual_sql,
            "judge": judge_result.model_dump(),
        })

    duration = time.time() - start

    baseline_results = None
    if args.baseline:
        bp = BASELINE_DIR / "main_latest.json"
        if bp.exists():
            baseline_results = json.loads(bp.read_text(encoding="utf-8"))

    report = build_report(results, duration, baseline=args.baseline, baseline_results=baseline_results)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = REPORT_DIR / f"{ts}_eval.{args.format}"
    out_path.write_text(report, encoding="utf-8")
    (REPORT_DIR / "latest.md").write_text(report, encoding="utf-8")
    print(f"Report: {out_path}")


if __name__ == "__main__":
    main()
```

### Task 3.2 补足 baseline 对比逻辑（V1 即出，不留 V2）
**说明**：Task 3.1 的 `build_report` 已含 baseline diff 分支。夜间全量跑完后，**写入 baseline**：
```python
# tests/golden/run_eval.py main() 末尾可选补充（夜间 cron 走）
if args.baseline == "--write-self-as-baseline":
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    (BASELINE_DIR / "main_latest.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
```
> CI 夜间任务走两轮：第一轮 `python -m tests.golden.run_eval` 生成报告；第二轮 `python -m tests.golden.run_eval --baseline=--write-self-as-baseline` 刷新 baseline。PR 走 `python -m tests.golden.run_eval --subset --baseline=main` 只读。

### Task 3.3 跑一次完整评测（子集）
```powershell
# 本地 smoke：默认走 mock 避免耗额度
$env:MOCK_LLM="1"
python -m tests.golden.run_eval --subset --limit=3
# 生产路径（需 GOOGLE_APPLICATION_CREDENTIALS 指向可用 vertex JSON）：
# Remove-Item Env:\MOCK_LLM
# python -m tests.golden.run_eval --subset
```
**预期**：生成 `tests/golden/reports/{ts}_eval.markdown`，含分数表 + 通过率。mock 路径下 verdict 全为 `review`（fallback_result 指定），本身为集成验收；生产路径下走真实评分。

### Phase 3 commit
```powershell
git add tests/golden/run_eval.py
git commit -m "feat(09): phase 3 eval CLI + baseline diff (V1 即出, da-agent class API)"
```

---

## Phase 4 — CI 集成 + 验收 + [complete]

### Task 4.1 创建 .github/workflows 目录 + workflow
**说明**：Phase 0 核对中 `.github/workflows/` 目录不存在，本 Task 创建。
```powershell
if (-not (Test-Path .github/workflows)) {
  New-Item -ItemType Directory -Path .github/workflows -Force
}
```
**Create**: `.github/workflows/eval.yml`
**完整代码**:
```yaml
name: Eval Subset
on:
  pull_request:
    paths:
      - 'data_acquisition_agent/**'
      - 'app/runtime_skills/**'
      - 'tests/golden/**'
      - 'tests/fixtures/golden/sql_generation/**'
      - 'app/core/model_client.py'
  schedule:
    - cron: '0 16 * * *'   # UTC 16:00 = CN 00:00

jobs:
  eval:
    runs-on: ubuntu-latest
    permissions:
      # v3.2 二轮 paranoid 修复：显式声明所需权限。
      # 默认 GITHUB_TOKEN 在仓库设置 "Read repository contents and packages permissions" 时
      # 不含 issues:write，PR comment 步骤会 403 Forbidden。这里显式声明保证在严格模式下也能工作。
      contents: read       # actions/checkout 需要
      issues: write        # PR comment 需要（actions/github-script 调 issues.createComment）
      pull-requests: write # 部分 GitHub 仓库设置下 PR comment 走 PR API 而非 issues API
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - name: Write GCP credentials
        env:
          GCP_KEY_JSON: ${{ secrets.GCP_KEY_JSON }}
        run: |
          # secrets.GCP_KEY_JSON 必须存放 GCP service account JSON 的完整内容（不是路径）。
          # workflow 运行时写入临时文件并 export GOOGLE_APPLICATION_CREDENTIALS 路径。
          echo "$GCP_KEY_JSON" > $HOME/key.json
          chmod 600 $HOME/key.json
          echo "GOOGLE_APPLICATION_CREDENTIALS=$HOME/key.json" >> $GITHUB_ENV
      - name: Run eval
        run: |
          if [ "${{ github.event_name }}" = "schedule" ]; then
            python -m tests.golden.run_eval
          else
            python -m tests.golden.run_eval --subset --baseline=main
          fi
      - name: Upload report artifact
        uses: actions/upload-artifact@v4
        with:
          name: eval-report
          path: tests/golden/reports/latest.md
      - name: Comment PR with report
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const report = fs.readFileSync('tests/golden/reports/latest.md', 'utf8');
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: report
            });
```

### Task 4.2 GitHub secrets 配置（项目负责人=admin role）
**责任人**: 项目负责人（需 repo admin 权限）。
**手动步骤**:
1. 在 GitHub repo Settings → Secrets and variables → Actions 加 secret，**名称必须为 `GCP_KEY_JSON`**（与 Task 4.1 workflow `env.GCP_KEY_JSON` 严格对齐）。
2. **Value = vertex 服务账号的完整 JSON 内容**（不是路径；workflow 会在运行时 `echo > $HOME/key.json` 写入临时文件并 export `GOOGLE_APPLICATION_CREDENTIALS`）。
3. 推一个测试 PR 验证 workflow 能绿。
4. **替代方案（admin 暂不可用）**：workflow 中双开环境变量 `MOCK_LLM=1`（`run` 步骤 `env: MOCK_LLM: "1"`），CI 先走 mock 验证集成。admin 到位后补真实 secret。

### Task 4.3 跑全量 50 条
```powershell
python -m tests.golden.run_eval
```
**预期**：生成报告，overall ≥ 3.5（V1 验收门槛）。
**预期耗时**（v3.1 补）：50 条 × 平均 8s/case≈ 7–9 分钟。单条 case 超过 60s 则由 Task 3.1 `run_actual_sql_gen` 的 `OrchestratorError / ValidationError` 捕获返空 SQL、Judge 打必 fail/review，不会拖垄整批跑。

### Task 4.4 Calibration drift 验证
**前置**：Phase 2 Task 2.5 `CALIBRATION_HUMAN_SCORES` 已填 5-10 条，且已设 `GOOGLE_APPLICATION_CREDENTIALS` 指向可用的 vertex 服务账号 JSON。
```powershell
# 可选：本地先 mock 趋完集成路径
# $env:MOCK_LLM="1"
# $env:GOOGLE_APPLICATION_CREDENTIALS="<路径到 vertex JSON>"
python -c "from tests.golden.calibration import calibrate; print(f'Drift: {calibrate():.2f}')"
```
**预期**：drift < 1.0。drift ∈ [1.0, 2.0] 调 rubric 措辞，drift > 2.0 回退（参§9.2）。

### Task 4.5 [complete] commit + push
```powershell
# v3.2 二轮 paranoid 修复：push 前**强制**跑 drift gate，避免 Judge 不可用还推到 main。
# Phase 4 Task 4.4 是手动触发，Task 4.5 push gate 自动校验，双保险。
$env:GOOGLE_APPLICATION_CREDENTIALS="<路径到 vertex JSON>"   # 真实校准必须 unset MOCK_LLM
Remove-Item Env:\MOCK_LLM -ErrorAction SilentlyContinue
$drift = python -c "from tests.golden.calibration import calibrate; print(f'{calibrate():.4f}')"
Write-Host "Calibration drift = $drift"
if ([float]$drift -gt 2.0) {
    Write-Error "drift=$drift > 2.0：Judge 不可用，触发 §9.2 回退预案，中止 push"
    exit 1
} elseif ([float]$drift -gt 1.0) {
    Write-Warning "drift=$drift ∈ (1.0, 2.0]：Judge 偏移，建议 commit 后立即调 rubric 措辞"
}

# v3.1 补：push 前必须校验 remote 指向、避免误推到错误仓库
git remote -v | Select-String 'origin\s+.*lizheng33193/MAPS-LZ'
if ($LASTEXITCODE -ne 0) { Write-Error 'origin 未指向 lizheng33193/MAPS-LZ，中止 push'; exit 1 }

git commit --allow-empty -m "[complete] plan-09 — eval system with rubric + ci"
git push origin main
```

---

## 五点检查法（自审）

| # | 检查项 | v2 | v3 | v3.1 | v3.2 |
|---|---|---|---|---|---|
| 1 | 精确文件路径 | ✅ | ✅ | ✅ | ✅ |
| 2 | 无占位符 | ✅ | ⚠️ Task 1.2 JSON 示例含 `//` 注释、落盘会报 JSONDecodeError | ✅ 修复：Task 1.2 改 `.jsonc` 示意 + 验证命令 | ✅ 保持 |
| 3 | 完整代码块 | ✅（调用不存在的 `client.generate()`） | ✅ 修复：judge.py / smoke / mock test 统一走 `generate_structured` | ✅ | ✅ |
| 4 | 验证命令 + 预期 | ✅ | ✅ 补充 mock vs vertex 模式标识 | ✅ 补 sqlglot None 检查 + Task 4.3 耗时预期 + MOCK_LLM 清理 | ✅ Task 0.1 加 requirements 依赖前置体检（缺 sqlglot/pydantic/google-genai 当场 `exit 1`） |
| 5 | 一个不熟悉项目的人能独立执行完 | ⚠️（API 调用会报 AttributeError） | ✅ 修复后可运行 | ⚠️ Phase 0 缺依赖体检 → Phase 4 workflow 才暴露缺包，浪费时间 | ✅ 修复：Phase 0 当场暴露缺包问题 |

---

## 回滚预案

```powershell
# 1) 关闭 CI workflow（注释 on:）
# 2) 仍不平 → git reset --hard {baseline_commit}
```

---

## 风险登记

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| LLM Judge 自洽偏见 | 中 | 高 | calibration 校准 + 人工抽查 10% |
| 评测集 expected SQL 错 | 中 | 中 | A + B 双人审，commit 注明 reviewed-by |
| da-agent generate() 超时 | 中 | 中 | Tenacity 重试，单条 case 超时记 verdict=fail |
| CI 跑评测 > 5 min | 中 | 中 | subset 10 条（PR） + 全量 50 条夜间跑 |
| LLM API 限流影响 CI | 低 | 中 | Tenacity 重试，失败 case verdict=review |

---

## 测试矩阵

| 类别 | 范围 | 触发 |
|---|---|---|
| Judge 单元（mock） | tests/golden/test_judge.py | Phase 2/4 |
| Calibration | tests/golden/calibration.py | Phase 4 |
| CLI 子集跑 | python -m tests.golden.run_eval --subset | Phase 3/4 |
| 全量回归 | tests/ | Phase 4 |
| CI workflow | PR + schedule | Phase 4 |

---

## TASK.md 记一行

```markdown
- [ ] Eval 体系（双国 50 条 NL→SQL）→ docs/plans/09-eval-system-plan.md
```
