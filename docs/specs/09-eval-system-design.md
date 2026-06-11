# Design Doc 09 — Eval 体系（双国 50 条 NL→SQL + Rubric + LLM Judge）

> **STATUS**: ✅ **READY-FOR-PLAN — v3.2** （v3.2 三轮无内容变更，仅同步 Plan 09 v3.2 的 Task 0.1 依赖前置体检；待用户最终复审后正式进入 Plan 执行）
>
> **v3.2 修订点**（对照 v3.1）：
> - 设计层无变更。Plan 09 v3.2 在 Phase 0 Task 0.1 加 `requirements.txt` 关键依赖（sqlglot / pydantic / google-genai）的前置体检，本 Spec 无需对应改动；记此版本号同步以保持 Spec / Plan 版本一致。
>
> **v3.1 二轮修订点**（对照 v3，保留供溯源）：
> - **§2.3 / §2.4 路径同步**：`expected_sql_path` 路径从 `golden_sqls/...` 改为 `expected_sqls/...`，与 Plan Task 1.2/1.3 一致。
> - **§4.4 calibration drift 语义同步**：伪代码从 `if drift > 1.0: raise` 改为 `return drift`，与 Plan Task 2.5 实际代码一致（drift 阈值处置语义走 §9.2 回退预案，不在 calibrate() 函数内 raise）。
> - **§6.1/6.2 workflow snippet 说明**：补一句「PR + schedule 两段 snippet 仅为说明，Plan Task 4.1 合并为单个 `eval.yml`」，避免误读为 2 个 yml。
>
> **v3 修订点**（对照 v2）：
> - **API 同步**：Spec §4.3 明确说明 LLM 调用走 `ModelClient.generate_structured(skill_name, prompt, fallback_result, response_schema=None, *, route_key=None)`，返回 dict 含 `status / structured_result / model_name / prompt_preview`。与 Plan v3 Task 2.3 实现一致。
> - **schemas 同步**：JudgeResult / RubricScores 从 judge.py 拆出到 `tests/golden/schemas.py`，与 Plan Task 2.2 一致。
> - **calibration 名同步**：§4.4 示例函数名 `calibrate_judge()` 改为 `calibrate(client=None) -> float`，与 Plan Task 2.5 一致。
> - **secret 名同步**：§6.1 workflow `secrets.GCP_KEY` 改为 `secrets.GCP_KEY_JSON`（JSON 内容不是路径），运行时 echo 写临时文件后 export `GOOGLE_APPLICATION_CREDENTIALS`；与 Plan Task 4.1/4.2 一致。
>
> **作者**: Codex / Claude（自动生成草稿）
> **日期**: 2026-05-05（v2 修订 2026-05-05） / 2026-05-06（v3 修订）
> **关联 Plan**: `docs/plans/09-eval-system-plan.md`（同步 v3）
> **依赖前置**: 无强前置（与 Plan 07 / Plan 08 可并行；本 Plan 仅复用 da-agent 公开类 API）
> **关联文档**:
> - Harness Engineering 学习笔记 §11 Eval 层（三层评估：结构验证 → Golden Test → Rubric）
> - `Agent搭建实战学习笔记.md` Q8 Rubric 评估完整代码
> - `tests/golden/` 现有评测框架（runner.py + 5 个 case_0X_*.json + judge_prompt.md + rubric.md）

## Surgical Hard Boundary（硬约束）

| 不动的目录/文件 | 原因 |
|---|---|
| `data_acquisition_agent/`（整目录）| 本 Plan 仅 import 调用 `DataAcquisitionOrchestrator` 公开 API，**绝不修改任何源文件** |
| `tests/golden/runner.py` | 现有评测运行器，本 Plan 复用而非替换 |
| `tests/fixtures/golden/behavior_profile/`（4 case） | 现有画像评测 fixture，不动 |
| `tests/fixtures/golden/comprehensive_profile/`（1 smoke case） | 现有融合评测 fixture，不动（注意目录名带 `_profile` 后缀）|

## ModelClient 强制声明

本 Plan 所有 LLM 调用**必经 `app/core/model_client.py::ModelClient`**（封装 Vertex Gemini + 重试 + 路由），**禁止直接 `import google-genai` 或裸 `requests` 调 API**。这是 CLAUDE.md「Zero Tolerance」第 5 条。

**v3 明确 API 套用**：唯一公开 LLM 调用入口是 `generate_structured(skill_name: str, prompt: str, fallback_result: dict, response_schema: dict | None = None, *, route_key: str | None = None) -> dict[str, Any]`。返回值为 `{"status": "ok"|"model_unavailable", "structured_result": dict, "model_name": str, "prompt_preview": str}`。`ModelClient` **不存在 `generate(prompt, route_key=...)` 方法**（v2 误寫、v3 修复）。

---

## 0. 背景与目标

### 0.1 现状（以 git HEAD `bd05240` 为准 — Phase 0 PowerShell 已核对）
- 项目**已有 Golden Test 评测框架**（含 runner、judge prompt、rubric md、5 个 case JSON）：
  - `tests/golden/runner.py`
  - `tests/golden/judge_prompt.md`
  - `tests/golden/rubric.md`
  - `tests/golden/case_01_loyal_th_user.json` ~ `case_05_query_data_mx.json`（5 个）
  - `tests/golden/__init__.py`
  - `tests/fixtures/golden/behavior_profile/*.json` （4 case）
  - `tests/fixtures/golden/comprehensive_profile/824812551379353600.json` （1 smoke case，注意目录名带 `_profile` 后缀）
- **但现有 Golden Test 仅覆盖画像输出**（behavior_profile 质量、comprehensive 融合），**不覆盖 NL→SQL 质量**
- 改 prompt **凭感觉**，没有量化指标
- 不知道哪次改动让效果变好/变差
- 每次改 prompt 都要人工跑 5-10 条样本目测

### 0.2 目标
- **在现有 Golden Test 框架上增建 NL→SQL 评测集**（不重复造轮子）
- **双国各 25 条 NL→SQL 评测集（共 50 条）**
- **Rubric 5 维分数稳定**（同 SQL 多次跑，方差 < 0.5）
- **改 prompt 前后跑评测集看 delta**（量化优化方向）
- **PR 自动跑 subset**（10 条，5 分钟内完成）
- **主分支夜间全量**（50 条）

### 0.3 设计依据：Harness §11 三层评估 + 现有框架复用

> 第一层：结构验证（Pydantic，零成本）→ 第二层：Golden Test（已知正确答案，准确率指标）→ 第三层：Rubric 多维打分（LLM Judge，质量指标）。三层叠加而非三选一。

本 Plan 主要落地第二层（Golden Test）+ 第三层（Rubric），第一层在 Plan 08 SQLJudge 已实现（L1 + L2）。

**复用现有框架**：
- 仍用 `tests/golden/runner.py` 已有的运行器（只补 NL→SQL 场景）
- 评测 fixture 补到 `tests/fixtures/golden/sql_generation/` 子目录（与 `behavior_profile/`、`comprehensive_profile/` 并列）
- 新增的 Rubric Judge 独立于 runner.py，都放 `tests/golden/judge.py`（不侵入 runner）
- CLI 入口放在 `tests/golden/run_eval.py`（不新建 `tests/eval/` 目录，避免双轨）

---

## 1. 范围与非目标

### 1.1 ✅ 范围内
| 项 | 说明 |
|---|---|
| 双国各 25 条评测集 | NL → 期望 SQL，覆盖 5 类难度 |
| Rubric 5 维评分 | 语法/语义/性能/安全/可读性 |
| LLM-as-Judge | gemini-2.5-flash（走现有 `gemini` provider，评分要稳） |
| 评测脚本 CLI | `python -m tests.golden.run_eval` |
| baseline 对比 | 跑前存当前 main 分支结果，对比 delta（V1 即出 delta，不留 V2） |
| CI 集成 | PR subset 10 条 + 夜间全量 50 条 |

### 1.2 ❌ 非目标
| 项 | 推迟到 | 理由 |
|---|---|---|
| run_profile / run_trace 等非 SQL 工具评测 | V2 | 先聚焦最大痛点（NL→SQL） |
| 自动调 prompt 优化 | V3 | 评测集是手动改 prompt 的工具，不是自动优化器 |
| 跨模型对比（mini vs pro） | V2 | V1 只评一个模型 |
| 评测结果可视化 dashboard | V2 | CLI + Markdown 报告够用 |

---

## 2. 评测集设计

### 2.1 数据规模

```
tests/
├── golden/                            # 现有目录（复用）
│   ├── runner.py                      # 现有运行器（不动）
│   ├── judge_prompt.md                # 现有（不动）
│   ├── rubric.md                      # 现有（不动）
│   ├── case_01_*.json ~ case_05_*.json # 现有 5 case（不动）
│   ├── judge.py                       # ✨ 新增：Rubric LLM Judge（Pydantic 校验）
│   ├── rubric.py                      # ✨ 新增：5 维评分定义
│   ├── schemas.py                     # ✨ 新增：JudgeResult / RubricScores
│   ├── calibration.py                 # ✨ 新增：人工 vs LLM 校准
│   ├── run_eval.py                    # ✨ 新增：CLI 入口
│   └── reports/                       # ✨ 新增：评测报告归档目录
├── fixtures/golden/
│   ├── behavior_profile/              # 现有 4 case（不动）
│   ├── comprehensive_profile/         # 现有 1 smoke case（不动，注意带 `_profile` 后缀）
│   └── sql_generation/                # ✨ 新增子目录
│       ├── eval_set.json              # 50 条主集
│       ├── eval_subset.json           # 10 条 PR 用子集
│       └── expected_sqls/
│           ├── mx/case_001.sql ~ case_025.sql
│           └── th/case_001.sql ~ case_025.sql
├── golden/baselines/                # ✨ baseline 存档
│   ├── main_latest.json
│   └── main_history/
└── test_golden_sql_generation.py    # ✨ 新增（调用 runner.py）
```

> 重点：**不新建 `tests/eval/` 目录**，避免与现有 `tests/golden/` 双轨。所有 NL→SQL 评测走 `tests/golden/` 子目录（CLI、judge、rubric、calibration、reports 全部）。fixture 走 `tests/fixtures/golden/sql_generation/`（与 `behavior_profile/`、`comprehensive_profile/` 并列）。

### 2.2 难度分布（5 类 × 5 条 / 国 = 25 条 / 国）

| 类别 | 占比 | 示例 |
|---|---|---|
| **simple_query** | 5 条 | "查询用户 824812551379353600 的基本信息" |
| **aggregation** | 5 条 | "最近 7 天注册用户总数" |
| **join** | 5 条 | "查询活跃用户的设备类型分布" |
| **time_window** | 5 条 | "本月 vs 上月 DAU 对比" |
| **edge_case** | 5 条 | "查询不存在的 UID（应返回空集）" |

### 2.3 评测集 schema

```json
// tests/golden/eval_set.json
[
  {
    "case_id": "mx_001",
    "country": "mx",
    "category": "simple_query",
    "difficulty": "easy",
    "nl_query": "查询用户 824812551379353600 的最近一次登录时间",
    "expected_sql_path": "expected_sqls/mx/case_001.sql",
    "tags": ["user_lookup", "timestamp"],
    "notes": "基础场景，应一次通过"
  },
  {
    "case_id": "mx_002",
    "country": "mx",
    "category": "aggregation",
    "difficulty": "medium",
    "nl_query": "最近 7 天每日新增用户数",
    "expected_sql_path": "expected_sqls/mx/case_002.sql",
    "tags": ["count", "group_by", "date_trunc"],
    "notes": "聚合 + 时间分组"
  }
  // ... 共 50 条
]
```

### 2.4 评测集准备流程

**第一步（人工，责任人=数据分析师）**: 用户从历史日志/真实需求中筛选 50 条代表性 NL query。

**「代表性」判定标准**（用户确认）：
1. 5 类难度（simple_query / aggregation / join / time_window / edge_case）每类 ≥ 5 条/国
2. 来源覆盖：实际线上需求 ≥ 60%（取自 da-agent 历史 request_id 日志），LLM 生成补足 ≤ 40%
3. 长度：NL query 字符数分布 P50 ∈ [20, 100]，P95 ≤ 300
4. 语言：mx 全西/中混（≥ 80% 中），th 全英/中混（≥ 80% 中）
5. 不重复：cosine 相似度 < 0.85（用 sentence-transformers 粗滤）

**第二步（半自动）**: 用 LLM（gemini-2.5-flash）生成 expected SQL → 人工审核修正。

**第三步（双人评审）**: 责任人=数据分析师 A + B（不同人），各自独立审核 50 条；分歧 case 由项目负责人裁决。每条 case 标注 tags + notes，补充测试用意。

---

## 3. Rubric 5 维（对应 Harness §11）

### 3.1 评分维度

| 维度 | 5 分 | 1 分 |
|---|---|---|
| **语法正确性** | SQL 能在 StarRocks 上跑通（sqlglot parse OK + 字段名存在） | 语法错误 / 字段拼写错 |
| **语义正确性** | 输出与 expected SQL 输出一致（行数、字段值匹配） | 完全不同的查询逻辑 |
| **性能** | 走索引 / 不必要的 JOIN 已避免 / LIMIT 合理 | 全表扫 / 子查询嵌套 > 3 层 |
| **安全** | 符合脱敏规则（无敏感字段明文）/ 无 DDL | 含 DDL / 暴露敏感字段 |
| **可读性** | 格式规范 / 别名清晰 / 注释合理 | 一行写完 / 别名 a/b/c |

### 3.2 评分标准（每维度 1-5 分）

```python
# tests/golden/rubric.py
RUBRIC_DIMENSIONS = {
    "syntax": {
        "5": "SQL 完全符合 StarRocks 语法，sqlglot parse 无错，字段名全部在 schema 中",
        "4": "SQL 语法正确，但有 1 个字段名拼写错误或边角问题",
        "3": "SQL 语法正确，但有 2-3 个字段问题",
        "2": "SQL 语法基本正确，但需要明显修改才能跑通",
        "1": "语法错误，无法 parse"
    },
    "semantics": {
        "5": "执行结果与 expected SQL 完全一致（行数、字段值匹配）",
        "4": "执行结果基本一致，仅排序/边界差异",
        "3": "查询逻辑接近 expected，但部分场景结果不同",
        "2": "查询逻辑偏离 expected 较多",
        "1": "完全不同的查询逻辑"
    },
    "performance": {
        "5": "走索引、JOIN 数量合理（≤ 3）、有 LIMIT、无嵌套子查询",
        "4": "性能可接受，1 个小问题（如可改 CTE）",
        "3": "性能一般，2-3 个性能问题",
        "2": "性能差，明显需优化",
        "1": "全表扫 / 嵌套深度 > 3 / JOIN > 5"
    },
    "security": {
        "5": "完全符合脱敏规则，无 DDL，无敏感字段（密码/token/手机号）暴露",
        "4": "有 1 个轻微敏感字段（如 user_id）但场景合理",
        "3": "可能有问题需要 review",
        "2": "暴露了 1 个敏感字段",
        "1": "含 DDL 或多个敏感字段暴露"
    },
    "readability": {
        "5": "格式规范、缩进合理、有意义的别名、必要的注释",
        "4": "格式良好，1 个小问题",
        "3": "可读性一般",
        "2": "格式混乱",
        "1": "无法快速理解逻辑"
    }
}
```

---

## 4. LLM-as-Judge 实现

### 4.1 模型选择

- **gemini provider 下的 gemini-2.5-flash**（`config.yaml::llm.providers.gemini.model = gemini-2.5-flash`）
- **不新增 `gemini_pro` / `gemini_flash` provider** — 统一走现有 `gemini` 路由，避免名字不一致
- **§1.1 表格已统一为 gemini-2.5-flash**（早期 v1 草稿误写 "gemini-pro"，与本节冲突；以本节为准）
- 路由键添加到 `config.yaml::llm.routes`： `eval.judge: gemini`（**平铺格式**，与现有 9 条路由保持一致；**不用** `{primary, fallback_chain}` 嵌套结构）
- 单次评测 token：~3K input + ~1K output ≈ $0.01 （gemini-2.5-flash 计费）
- Maestro Spike 通过后一行配置翻为 `eval.judge: claude_maestro` 以提质
- **mock 降级**：`config.yaml::llm.providers.mock` 已存在，单元测试与 CI dry-run 走 mock，不调真实 LLM

### 4.2 Judge Prompt 模板

```python
JUDGE_PROMPT = """你是一个 SQL 评测专家。请按以下 Rubric 对 actual SQL 打分。

## 评测案例
- NL Query: {nl_query}
- Country: {country}
- Category: {category}

## Expected SQL（黄金标准）
```sql
{expected_sql}
```

## Actual SQL（待评测）
```sql
{actual_sql}
```

## 评分标准（每维度 1-5 分）
{rubric_definitions}

## 输出格式（严格 JSON）
{{
  "scores": {{
    "syntax": 1-5,
    "semantics": 1-5,
    "performance": 1-5,
    "security": 1-5,
    "readability": 1-5
  }},
  "reasoning": {{
    "syntax": "...",
    "semantics": "...",
    "performance": "...",
    "security": "...",
    "readability": "..."
  }},
  "overall": <1-5 平均分，保留 1 位小数>,
  "verdict": "pass" | "fail" | "review"   // overall ≥ 4.0=pass, < 3.0=fail, 否则 review
}}
"""
```

### 4.3 Judge 输出 Pydantic 校验

```python
# tests/golden/schemas.py（v3 从 judge.py 拆出，与 Plan Task 2.2 一致）
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

### 4.3.1 LLM 调用送受路径（v3 新增）

```python
# tests/golden/judge.py（v3 重写）
from app.core.model_client import ModelClient

result = client.generate_structured(
    skill_name="eval_judge",
    prompt=prompt,
    fallback_result={
        "scores": {"syntax": 1, "semantics": 1, "performance": 1, "security": 1, "readability": 1},
        "reasoning": {dim: "model_unavailable" for dim in ("syntax", "semantics", "performance", "security", "readability")},
        "overall": 1.0,
        "verdict": "review",
    },
    response_schema=_JUDGE_RESPONSE_SCHEMA,
    route_key="eval.judge",
)
# result["status"] ∈ {"ok", "model_unavailable"}
# result["structured_result"] 是模型输出 dict（或 fallback）
payload = result["structured_result"]
return JudgeResult(**payload)  # 走 Pydantic 二阶校验
```

### 4.4 Judge 自身可靠性验证

**问题**: LLM Judge 可能不稳定（同一 SQL 多次评分差异大）

**验证方法**:
1. 选 5-10 个 case 用人工打分（**Plan Phase 2 会实际填表**，不留空骨架）
2. 对比人工 vs LLM 打分
3. 偏差 > 1 分 → 调 rubric 措辞 / 增加 few-shot 示例

**drift 阈值来源**：参考 `Agent搭建实战学习笔记.md` Q8 — 5 维各 1-5 分，绝对值差 1.0 = 单维错 1 档（如把 "5" 打成 "4"），可接受；> 1.0 → 系统性偏移；> 2.0 → Judge 不可用必须回退。

```python
# tests/golden/calibration.py（CLI 路径已与 Plan 统一在 tests/golden/）
def calibrate(client=None) -> float:
    """v3.1：返回平均偏差（drift）、**不在函数内 raise**；CALIBRATION_HUMAN_SCORES 为空则 RuntimeError。
    drift 阈值处置语义走 §9.2 回退预案：> 1.0 调 rubric / > 2.0 关闭压缩。与 Plan Task 2.5 实现一致。"""
    if not CALIBRATION_HUMAN_SCORES:
        raise RuntimeError("CALIBRATION_HUMAN_SCORES 为空。Plan Phase 2 Task 2.5 未完成。")
    diffs: list[float] = []
    for entry in CALIBRATION_HUMAN_SCORES:
        # … 加载 expected_sql 后 走 run_judge，逐维度取 abs(llm - human) 入 diffs
        ...
    return sum(diffs) / len(diffs) if diffs else 0.0
```

---

## 5. 评测脚本 CLI

### 5.1 命令行接口

```bash
# 全量评测
python -m tests.golden.run_eval

# 子集评测（PR 用）
python -m tests.golden.run_eval --subset

# 单国
python -m tests.golden.run_eval --country=mx
python -m tests.golden.run_eval --country=th

# 限制条数
python -m tests.golden.run_eval --limit=10

# 对比基线（V1 即出 delta）
python -m tests.golden.run_eval --baseline=main --branch=feature/sql-judge

# 输出格式
python -m tests.golden.run_eval --format=json    # 默认 markdown
```

### 5.2 输出格式

```markdown
<!-- tests/golden/reports/20260505_143022_main_vs_branch.md -->
# Eval Report — 2026-05-05 14:30:22

## 元信息
- Baseline: main @ c4f177f
- Branch: feature/sql-judge @ a1b2c3d
- Total cases: 50 (mx 25 + th 25)
- Duration: 4 min 32 s

## 总体分数

| 维度 | Baseline | Branch | Δ |
|---|---|---|---|
| syntax | 4.2 | 4.7 | **+0.5** ✅ |
| semantics | 3.8 | 4.1 | +0.3 ✅ |
| performance | 3.5 | 4.3 | **+0.8** ✅ |
| security | 4.5 | 4.9 | +0.4 ✅ |
| readability | 4.0 | 4.0 | 0 |
| **overall** | **4.0** | **4.4** | **+0.4** ✅ |

## 通过率

| 项 | Baseline | Branch |
|---|---|---|
| pass (overall ≥ 4.0) | 36/50 (72%) | 42/50 (84%) |
| fail (overall < 3.0) | 5/50 (10%) | 2/50 (4%) |

## 退步的 case（Branch 比 Baseline 差）

| Case | Δ | Baseline | Branch | 原因 |
|---|---|---|---|---|
| mx_018 | -0.6 | 4.2 | 3.6 | 性能下降，多了不必要的 JOIN |

## 进步的 case（Branch 比 Baseline 好）

| Case | Δ | Baseline | Branch |
|---|---|---|---|
| mx_007 | +1.4 | 2.6 | 4.0 |
| ... |
```

### 5.3 baseline 存储策略

```
tests/golden/baselines/
├── main_latest.json    ← 主分支最新评测结果（夜间全量更新）
└── main_history/       ← 历史记录
    └── 20260504_main_full.json
```

每次跑评测前先 `git fetch main` 取最新基线。

---

## 6. CI 集成（对应 Harness §12 Hooks）

> **v3.1 说明**：§6.1 + §6.2 为说明型两段 snippet，**不是两个 yml 文件**。Plan Task 4.1 合并为单个 `.github/workflows/eval.yml`，同时含 `pull_request:` + `schedule:` 两段触发。

### 6.1 PR 触发（subset 10 条，5 分钟内）

```yaml
# .github/workflows/eval.yml（仓库**当前没有** .github/workflows/ 目录，Plan Phase 4 Task 4.1 需创建）
name: Eval Subset
on:
  pull_request:
    paths:
      - 'data_acquisition_agent/**'
      - 'app/runtime_skills/**'
      - 'tests/golden/**'
      - 'tests/fixtures/golden/sql_generation/**'

jobs:
  eval:
    runs-on: ubuntu-latest
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
          # secrets.GCP_KEY_JSON 必须存放 GCP service account JSON 完整内容（不是路径）。
          echo "$GCP_KEY_JSON" > $HOME/key.json
          chmod 600 $HOME/key.json
          echo "GOOGLE_APPLICATION_CREDENTIALS=$HOME/key.json" >> $GITHUB_ENV
      - name: Run eval subset
        run: python -m tests.golden.run_eval --subset --baseline=main
      - name: Comment PR with delta
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
            })
```

### 6.2 主分支夜间全量

```yaml
on:
  schedule:
    - cron: '0 16 * * *'   # UTC 16:00 = 北京 00:00

jobs:
  nightly_eval:
    # ... 跑全量 50 条 + 更新 baselines/main_latest.json
```

---

## 7. 开放问题

### 7.1 expected SQL 谁来写？
- 选项 A：人工逐条写
- 选项 B：LLM 一次性生成 + 人审
- 选项 C：从历史日志中筛选已 ack 通过的 SQL

> **推荐**: C（历史日志） + B（不足部分 LLM 生成 + 人审）

### 7.2 LLM Judge 评分稳定性怎么保证？
- 选项 A：每条 case 跑 3 次取中位数
- 选项 B：单次 + temperature=0
- 选项 C：calibration_set 校准 + 单次

> **推荐**: C（calibration + 单次），成本可控。

### 7.3 评测失败时是否阻止 PR merge？
- 选项 A：阻止（overall < 3.5 的 case 数 > 5 时 fail）
- 选项 B：仅 comment 不阻止（人工判断）

> **推荐**: B（仅 comment），V1 评测不够稳，避免误伤。

---

## 8. 验收清单

### 8.1 Phase 0（baseline）
- [ ] `tests/golden/` 实际目录结构摸清（`Get-ChildItem tests/golden/`）
- [ ] `ModelClient` 支持 `route_key="orchestrator_agent.decide"` 调用（测试一次）
- [ ] `tests/golden/reports/`、`tests/golden/baselines/main_history/` 子目录创建（`tests/eval/` 不创建）
- [ ] `.github/workflows/` 目录核对（**当前不存在**，Phase 4 创建）

### 8.2 Phase 1（评测集）
- [ ] `tests/fixtures/golden/sql_generation/eval_set.json` 50 条就位（mx 25 + th 25）
- [ ] `tests/fixtures/golden/sql_generation/expected_sqls/{mx,th}/` 50 个 .sql 文件就位
- [ ] `tests/fixtures/golden/sql_generation/eval_subset.json` 10 条子集就位
- [ ] 双人审责任人 A + B 实名签字（commit message 注明）

### 8.3 Phase 2（Rubric + Judge）
- [ ] `tests/golden/rubric.py` Rubric 定义
- [ ] `tests/golden/judge.py` LLM Judge + Pydantic 校验
- [ ] `tests/golden/calibration.py` 校准脚本
- [ ] `CALIBRATION_HUMAN_SCORES` **实际填入 5-10 条**（不允许空列表 ship）
- [ ] Calibration drift < 1.0（人工 vs LLM）

### 8.4 Phase 3-4（CLI + CI）
- [ ] `tests/golden/run_eval.py` CLI 实现
- [ ] Markdown 报告输出格式正确
- [ ] baseline 对比逻辑可用（V1 即出 delta，对应 Spec §5.2）
- [ ] `.github/workflows/eval.yml` PR 触发跑通
- [ ] 夜间全量 cron 跑通
- [ ] PR 自动 comment delta 报告

---

## 9. 风险与回退预案

### 9.1 已知风险

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| LLM Judge 自洽偏见（自己写的觉得好） | 中 | 高 | calibration_set 校准；人工抽查 10% |
| 评测集本身有错（expected SQL 错了） | 中 | 中 | 双人审；首版只标 80 分置信度 |
| CI 跑评测耗时太长（> 5 min） | 中 | 中 | subset 10 条 + 并行调用 LLM |
| LLM API 限流影响 CI | 低 | 中 | retry + 指数退避（Tenacity） |

### 9.2 回退预案

**触发条件**: Calibration drift > 2.0（Judge 完全不可靠）

**回退步骤**:
1. 关闭 CI 评测（注释 workflow 触发条件）
2. 重新调 Rubric 措辞 + 增加 few-shot
3. drift < 1.0 后再开启

---

## 10. 参考文档

- Harness Engineering 学习笔记 §11 Eval 层
- `Agent搭建实战学习笔记.md` Q8 Rubric 评估
- `golden-test-design.md`（项目已有的 golden test 设计可借鉴）
