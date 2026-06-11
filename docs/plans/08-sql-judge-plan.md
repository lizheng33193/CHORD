# Plan 08 — SQLJudge（L1 规则 + L2 LLM + 反思循环）

> **STATUS**: ⚠️ DRAFT — 待用户五点检查法审核后改为 `READY-TO-EXECUTE`（**v3 范围对齐**：与 Plan 07 v3 同步收敛 V1 = mx + th 双国）
>
> **v3 修订点**（2026-05-06 用户范围决策同步）：
> - **Task 4.5 `test_schema_loader.py`**：v2 测试 5 国 × 1 unknown = 6 案例，但用户决策 V1 仅做 mx + th 双国，indonesia / pakistan / philippines 暂不在 V1 范围；v3 删除 `test_indonesia_falls_back_to_yaml` / `test_pakistan_falls_back_to_yaml` / `test_philippines_falls_back_to_yaml` 3 个 test 函数，保留 mx + th + unknown sentinel = 3 案例。fallback 链保留作为未来扩展接口（不动 wrapper 代码），未来扩展时只需把对应 test 函数加回来即可。
> - **wrapper `_load_schema_for_judge` docstring**：「5 国都能命中 `<country>.yaml`」→「V1 mx + th 命中；其余 3 国保留作为未来扩展接口」。
> - **风险登记 + 五点检查法第 4 项 验证命令描述**：「5 国 schema fallback」→「V1 双国 schema fallback (mx + th + unknown sentinel)」。
>
> **作者**: Codex / Claude（自动生成草稿）
> **日期**: 2026-05-05（v2） / 2026-05-06（v3 与 Plan 07 v3 同步收敛 V1 范围）
> **关联 Spec**: `docs/specs/08-sql-judge-design.md`
> **HEAD baseline**: 待 Plan 07 完成后确定
> **预计 Phase 数**: 4

---

## 0. Baseline 共识

### 0.1 关联文档
- Spec: `docs/specs/08-sql-judge-design.md`
- `PLANNING.md` 已知约束 7 条（SQL/凭据安全 + DA artifact 安全 + Surgical Hard Boundary）
- `CLAUDE.md` 关键约束（不执行 SQL / 不连数据库）

### 0.2 关键约束（Surgical Hard Boundary）
- `data_acquisition_agent/orchestrator.py` 与其他 11 个核心 .py **不能修改**（164 tests 锁定区）
- 本 Plan 采用 **Sidecar Wrapper 模式**：新建 `data_acquisition_agent/sql_judge/` 子目录与 `wrapper.py`，包装原 orchestrator；切换调用仅限 `app/services/orchestrator_agent/tools/query_data.py` 的 **import 行 + 实例化行**（合计 2 行）
- L1+L2 通过的 SQL **仍是待审核 artifact**，走 V2 `/execute` 人工 ack 入口（不自动 ack）
- LLM 调用必经 `app/core/model_client.ModelClient.generate_structured()`，**不直接 import google-genai，也不存在 `client.generate(prompt, ...)` 这个方法**
- 凭据扫描位于原 orchestrator `_enforce_output_policies`（调 `scan_credentials`），**本 Plan L1/L2 不重复扫凭据**
- **开放问题 — sidecar 物理位置**（Spec § 4.3 已描述，默认 A）：`data_acquisition_agent/sql_judge/`（默认选项、本 Plan 按该位置写）。**R7-H1 修复**：必须先在 Phase 0 Task 0.0 通过 `STOP-AND-CONFIRM` 显式拍板（用户回 A 或 B），否则不进 Task 0.1。如最终选 B (`app/services/sql_judge/`)，本 Plan 全量路径需同步调整

### 0.3 baseline commit
```powershell
git commit --allow-empty -m "[baseline] plan-08 — before execution"
```

### 0.4 测试矩阵
- 单元：L1 规则 / L2 LLM mock / 反思循环 / SQL_JUDGE_ENABLED=0 happy path
- 集成：DataAcq 现有 164 tests 不破
- 评测：依赖 Plan 09 评测集（如 09 未完成则跳过此项）
- schema 文本依赖：依赖 Plan 07（knowledge_base 精简版）。本 Plan V1 stub 路径 = `data_acquisition_agent/configs/<country>.local.yaml → <country>.yaml`（C2/C3 修复后）。详见 Spec § 4.3 `_load_schema_for_judge` 与 Plan Task 4.5 验收。

---

## 1. 范围

### 1.1 ✅ 包含
- L1 正则黑名单（DDL/DML 危险）
- L1 sqlglot AST 静态分析
- L2 gemini-flash LLM 审查 + Pydantic 校验
- SQLGen ↔ Judge 反思循环（max 3 轮）
- 集成到 DataAcq orchestrator ack 路径
- env var `SQL_JUDGE_ENABLED` 开关

### 1.2 ❌ 不包含
- 真正执行 SQL（V2+）
- EXPLAIN 性能分析（V2）
- ML 风险评分（V3）

---

## Phase 0 — Baseline 核对

### Task 0.0 sidecar 物理位置用户确认门（R7-H1 修复，阻塞后续 Task）

**背景**：Spec § 4.3 已推荐 A = `data_acquisition_agent/sql_judge/`，但属于 Surgical Hard Boundary 的**边界澄清问题**（CLAUDE.md 「不修改 data_acquisition_agent/ 下任何文件」与 query_data.py docstring 「不动 data_acquisition_agent 任何文件」措辞均可读为「整个包」）。**未获用户显式确认之前不得进入 Task 0.1**。

**选项请用户选择**：
- [ ] 候选 A（默认，Round 1-6 评估后的推荐项）：`data_acquisition_agent/sql_judge/`。仅新增子目录，11 个核心 .py 一字不动。
- [ ] 候选 B：`app/services/sql_judge/`。包边界零歧义，代价 = 跨包 import + audit 路径变长。

**如用户选 B**，必须同步调整以下全部位置（grep 验证零遗漏）：
```powershell
# 11+ 处路径替换错误检查：以下应返回 0 行
Get-Content docs/plans/08-sql-judge-plan.md, docs/specs/08-sql-judge-design.md | Select-String "data_acquisition_agent/sql_judge" | Measure-Object -Line
# wrapper.py 内依 configs 路径调整：
#   parents[1] / "configs"  (A 路径下)  →  parents[2] / "data_acquisition_agent" / "configs"  (B 路径下)
```

**STOP-AND-CONFIRM**（Hard Boundary 确认门）：
本 Plan **绝不自动假设默认 A**。文档内代码示例按 A 路径写仅为加载进度的占位，**不代表隐含同意**。
**未获用户在 Phase 0 Task 0.0 明确口头回复"选择 A"或"选择 B"之前，AI 禁止进入 Task 0.1**。
无回复 = 继续等待。Task 0.1 入口处必须先确认 session 上下文中存在用户的显式回复，否则停下重新询问。
如选 B (`app/services/sql_judge/`)，wrapper.py 中 `cfg_dir = Path(__file__).resolve().parents[1] / "configs"` 必须改为 `Path(__file__).resolve().parents[2] / "data_acquisition_agent" / "configs"`（Spec § 4.3 已注明）。

### Task 0.1 核对 orchestrator ack 路径 + Sidecar 接入点
```powershell
Get-Content data_acquisition_agent/orchestrator.py | Select-String "def generate|GenerateResponse|_enforce_output_policies" | Select-Object -First 20
Get-Content app/services/orchestrator_agent/tools/query_data.py | Select-String "DataAcquisitionOrchestrator|_orch" | Select-Object -First 10
Get-Content app/services/orchestrator_agent/ack_bus.py | Select-String "def " | Select-Object -First 5
```
**记录**：
1. `DataAcquisitionOrchestrator.generate(request: GenerateRequest) -> GenerateResponse`（返回 Pydantic 实例，**不是 dict**）
2. ack 逻辑位于 `app/services/orchestrator_agent/ack_bus.py` + `agent_loop.py`，**不在 `data_acquisition_agent/`**
3. `tools/query_data.py` 中 `DataAcquisitionOrchestrator` 出现 2 处：L17 import + L54 `self._orch = DataAcquisitionOrchestrator()`。本 Plan Task 4.2 需同时修改 2 处。

### Task 0.2 添加依赖（surgical 只装 sqlglot，不 touch 其他包）
**Modify**: `requirements.txt`
**追加**:
```
sqlglot>=18.0.0
```
**验证**（覆盖 V1 实际使用的 AST 节点：SELECT * / WHERE / LIMIT / JOIN / Star）:
```powershell
pip install "sqlglot>=18.0.0"   # surgical：不走 -r requirements.txt全量 reinstall
python -c "import sqlglot; print('sqlglot', sqlglot.__version__)"
python -c "import sqlglot; from sqlglot import exp; p = sqlglot.parse_one('SELECT 1', dialect='starrocks'); print(p)"
python -c "import sqlglot; from sqlglot import exp; p = sqlglot.parse_one('SELECT * FROM t WHERE x=1 LIMIT 10', dialect='starrocks'); print(any(isinstance(e, exp.Star) for e in p.expressions), p.args.get('limit') is not None, p.args.get('where') is not None)"
python -c "import sqlglot; print(sqlglot.parse_one('SELECT a FROM t1 JOIN t2 ON t1.id=t2.id', dialect='starrocks'))"
```
**预期**:
- 第一条输出版本号≥ 18.0.0
- 第二条输出为 `SELECT 1` 的 AST 表示
- 第三条输出三个 `True`（Star/limit/where 均正确检出）
- 第四条能正常 parse JOIN，不报异常

### Task 0.3 准备 50 个 SQL 测试样例（DDL block + safe allow）

> ⚠️ **预先创建测试子目录**（P3-2 修复）：`tests/data_acquisition_agent/` 本仓库当前 **不存在**（验证：`Test-Path tests/data_acquisition_agent` = False）。后续 Task 0.3 / 1.4 / 2.4 / 3.2 / 4.5 / 4.6 均在此子路径下创建文件。若使用不自动建父目录的工具（如裸 `Set-Content`）会报错。本步骤为预创建所有需要的父目录：
```powershell
New-Item -ItemType Directory -Force -Path tests/data_acquisition_agent/sql_judge_fixtures, tests/data_acquisition_agent/sql_judge | Out-Null
```

**Create**: `tests/data_acquisition_agent/sql_judge_fixtures/ddl_samples.json`
**完整 50 条**（M1 修复：Plan 全量 enumeration，无占位符）：
```json
[
  {"sql": "DROP TABLE users", "expected_block": true},
  {"sql": "DROP TABLE IF EXISTS users", "expected_block": true},
  {"sql": "DROP DATABASE prod", "expected_block": true},
  {"sql": "DROP SCHEMA mexico", "expected_block": true},
  {"sql": "DROP VIEW v_users", "expected_block": true},
  {"sql": "DROP INDEX idx_uid ON users", "expected_block": true},
  {"sql": "drop table tmp_t", "expected_block": true},
  {"sql": "TRUNCATE users", "expected_block": true},
  {"sql": "TRUNCATE TABLE users", "expected_block": true},
  {"sql": "TRUNCATE TABLE  users", "expected_block": true},
  {"sql": "ALTER TABLE users ADD COLUMN x INT", "expected_block": true},
  {"sql": "ALTER TABLE users DROP COLUMN c", "expected_block": true},
  {"sql": "ALTER DATABASE prod RENAME TO prod_new", "expected_block": true},
  {"sql": "ALTER SCHEMA s OWNER TO admin", "expected_block": true},
  {"sql": "CREATE TABLE tmp AS SELECT 1", "expected_block": true},
  {"sql": "CREATE TABLE tmp (id INT)", "expected_block": true},
  {"sql": "CREATE DATABASE staging", "expected_block": true},
  {"sql": "CREATE SCHEMA s2", "expected_block": true},
  {"sql": "CREATE VIEW v_active AS SELECT user_id FROM users WHERE active=1", "expected_block": true},
  {"sql": "GRANT SELECT ON users TO bob", "expected_block": true},
  {"sql": "GRANT INSERT ON users TO bob", "expected_block": true},
  {"sql": "GRANT ALL ON users TO admin", "expected_block": true},
  {"sql": "REVOKE SELECT ON users FROM bob", "expected_block": true},
  {"sql": "REVOKE ALL ON users FROM bob", "expected_block": true},
  {"sql": "REVOKE INSERT ON users FROM bob", "expected_block": true},
  {"sql": "DELETE FROM users", "expected_block": true},
  {"sql": "DELETE FROM transactions", "expected_block": true},
  {"sql": "DELETE FROM events", "expected_block": true},
  {"sql": "UPDATE users SET name='x'", "expected_block": true},
  {"sql": "UPDATE orders SET status='cancelled'", "expected_block": true},
  {"sql": "UPDATE events SET event_type='unknown'", "expected_block": true},
  {"sql": "DELETE FROM users WHERE id=1", "expected_block": true},
  {"sql": "DELETE FROM users WHERE created_at < '2025-01-01'", "expected_block": true},
  {"sql": "DELETE FROM orders WHERE user_id=123", "expected_block": true},
  {"sql": "UPDATE users SET name='x' WHERE id=1", "expected_block": true},
  {"sql": "UPDATE users SET email='x' WHERE user_id=123", "expected_block": true},
  {"sql": "UPDATE orders SET status='shipped' WHERE id=999", "expected_block": true},
  {"sql": "SELECT * FROM users", "expected_block": true},
  {"sql": "SELECT * FROM transactions", "expected_block": true},
  {"sql": "SELECT * FROM users, orders", "expected_block": true},
  {"sql": "SELECT user_id, name FROM users WHERE id=1 LIMIT 10", "expected_block": false},
  {"sql": "SELECT id, status FROM orders WHERE created_at > '2026-01-01' LIMIT 100", "expected_block": false},
  {"sql": "SELECT count(*) FROM users WHERE active=1", "expected_block": false},
  {"sql": "SELECT user_id FROM users WHERE id IN (1,2,3)", "expected_block": false},
  {"sql": "SELECT * FROM users LIMIT 10", "expected_block": false},
  {"sql": "SELECT * FROM users WHERE id=1", "expected_block": false},
  {"sql": "SELECT a.user_id, b.amount FROM accounts a JOIN balances b ON a.id=b.account_id LIMIT 50", "expected_block": false},
  {"sql": "SELECT user_id FROM users WHERE created_at BETWEEN '2026-01-01' AND '2026-02-01' LIMIT 1000", "expected_block": false},
  {"sql": "SELECT user_id, email FROM users WHERE phone LIKE '+52%' LIMIT 100", "expected_block": false},
  {"sql": "SELECT count(distinct user_id) FROM events WHERE event_type='login' LIMIT 1", "expected_block": false}
]
```

**分布统计**（R7-M2 修复：V1 scope=query_only/EXTRACT，全 DML block）：
- DDL block 25 条：DROP × 7 / TRUNCATE × 3 / ALTER × 4 / CREATE × 5 / GRANT × 3 / REVOKE × 3
- DML block 12 条（DELETE × 6 全部、UPDATE × 6 全部 — 不区分是否带 WHERE，与 `output_scanner.py` query_only 政策严格对齐）
- SELECT * block via AST 3 条（无 WHERE 无 LIMIT）
- safe SELECT allow 10 条（含 SELECT * + LIMIT × 1 + SELECT * + WHERE × 1 → AST 走 warn 路径，verdict ≠ block）

**已与 [rules.py](data_acquisition_agent/sql_judge/rules.py) 正则 + [ast_analyzer.py](data_acquisition_agent/sql_judge/ast_analyzer.py) AST 一一对账**（R7-M2 叠加）：
- V1 scope=query_only：全部 DELETE/UPDATE/INSERT 都 block（`\bDELETE\s+FROM\s+` / `\bUPDATE\s+\w+\s+SET\b` / `\bINSERT\s+INTO\s+` 三条正则覆盖，不再区分是否带 WHERE）
- `SELECT * FROM users LIMIT 10` AST 走 warn 路径（has_limit=True）→ verdict="warn" ≠ block → expected_block=false 正确
- `SELECT count(*) FROM users WHERE active=1` 中 `count(*)` 在 AST 中是 `exp.Count` 不是顶层 `exp.Star`，不触发 SELECT * 检查

**验证命令**：
```powershell
python -c "import json; data = json.load(open('tests/data_acquisition_agent/sql_judge_fixtures/ddl_samples.json',encoding='utf-8')); print('total:', len(data), 'block:', sum(1 for s in data if s['expected_block']), 'allow:', sum(1 for s in data if not s['expected_block']))"
```
**预期**：`total: 50 block: 40 allow: 10`

### Phase 0 commit
```powershell
git add requirements.txt tests/data_acquisition_agent/sql_judge_fixtures/ddl_samples.json
git commit -m "chore(08): phase 0 baseline + sqlglot dep + 50 ddl fixtures"
```

---

## Phase 1 — L1 规则引擎

### Task 1.1 实现 rules.py
**Create**: `data_acquisition_agent/sql_judge/__init__.py`（空）
**Create**: `data_acquisition_agent/sql_judge/rules.py`
**完整代码**:
```python
"""L1 SQL safety rules — regex blacklist (Plan 08 Phase 1).

R7-M2 修复：V1 scope = query_only / EXTRACT only。L1 黑名单与 `output_scanner.py`
query_only 政策严格对齐：全部 DELETE/UPDATE/INSERT block，不再区分是否带 WHERE。
build_table_script artifact 含 CREATE/DROP 是 intended，由 wrapper 跳过 judge。
"""
import re

DDL_BLACKLIST = [
    r"\bDROP\s+(TABLE|DATABASE|SCHEMA|VIEW|INDEX)\b",
    r"\bTRUNCATE\s+(TABLE\s+)?\w+",
    r"\bALTER\s+(TABLE|DATABASE|SCHEMA)\b",
    r"\bCREATE\s+(TABLE|DATABASE|SCHEMA|VIEW)\b",
    r"\bGRANT\s+",
    r"\bREVOKE\s+",
]

# R7-M2: V1 scope=query_only → 全 DML block（不仅限于无 WHERE）
DML_DANGEROUS = [
    r"\bDELETE\s+FROM\s+",   # 任何 DELETE FROM
    r"\bUPDATE\s+\w+\s+SET\b",   # 任何 UPDATE ... SET
    r"\bINSERT\s+INTO\s+",   # 任何 INSERT INTO（R7 新增，原沉默与 output_scanner 不一致）
]


def check_blacklist(sql: str) -> tuple[bool, str | None]:
    sql_normalized = re.sub(r'\s+', ' ', sql.strip())
    for pattern in DDL_BLACKLIST:
        if re.search(pattern, sql_normalized, re.IGNORECASE):
            return False, f"DDL 被禁止：匹配模式 {pattern}"
    for pattern in DML_DANGEROUS:
        if re.search(pattern, sql_normalized, re.IGNORECASE):   # R7-M2: 不再需要 DOTALL，无 lookahead
            return False, f"危险 DML（V1 scope=query_only）：匹配模式 {pattern}"
    return True, None
```

### Task 1.2 实现 ast_analyzer.py
**Create**: `data_acquisition_agent/sql_judge/ast_analyzer.py`
**完整代码**:
```python
"""L1 SQL AST analyzer — sqlglot-based (Plan 08 Phase 1)."""
import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError


def analyze_ast(sql: str) -> tuple[bool, list[str]]:
    try:
        parsed = sqlglot.parse_one(sql, dialect="starrocks")
    except SqlglotError as e:
        # v3.2 二轮 paranoid 修复：精准捕获 sqlglot 全部子类（ParseError / TokenError / OptimizeError 等）。
        # 不用宽 `except Exception`，避免误吞 SystemExit / KeyboardInterrupt / GeneratorExit
        # 等系统级异常，导致进程无法中断。
        return False, [f"SQL 语法错误：{type(e).__name__}: {e}"]

    warnings = []
    block_reasons = []

    selects = list(parsed.find_all(exp.Select))
    for sel in selects:
        is_star = any(isinstance(e, exp.Star) for e in sel.expressions)
        has_limit = sel.args.get("limit") is not None
        has_where = sel.args.get("where") is not None
        if is_star and not has_limit and not has_where:
            block_reasons.append("SELECT * 同时缺少 WHERE 和 LIMIT，可能全表扫")
        elif is_star and not has_limit:
            warnings.append("SELECT * 缺少 LIMIT，建议加 LIMIT 1000")

    joins = list(parsed.find_all(exp.Join))
    if len(joins) > 5:
        warnings.append(f"JOIN 数量 {len(joins)}，性能可能差")

    if block_reasons:
        return False, block_reasons
    return True, warnings
```

### Task 1.3 实现 L1 综合判定
**Create**: `data_acquisition_agent/sql_judge/l1.py`
**完整代码**:
```python
"""L1 综合判定 (Plan 08 Phase 1)."""
from typing import Literal, TypedDict
from .rules import check_blacklist
from .ast_analyzer import analyze_ast


class L1Result(TypedDict):
    verdict: Literal["allow", "block", "warn"]
    reason: str | None
    warnings: list[str]


def l1_check(sql: str) -> L1Result:
    blacklist_pass, bl_reason = check_blacklist(sql)
    if not blacklist_pass:
        return {"verdict": "block", "reason": bl_reason, "warnings": []}

    ast_pass, ast_msgs = analyze_ast(sql)
    if not ast_pass:
        return {"verdict": "block", "reason": "; ".join(ast_msgs), "warnings": []}

    if ast_msgs:
        return {"verdict": "warn", "reason": None, "warnings": ast_msgs}

    return {"verdict": "allow", "reason": None, "warnings": []}
```

### Task 1.4 unit test 覆盖 100% DDL
**Create**: `tests/data_acquisition_agent/sql_judge/test_l1.py`
**完整代码**:
```python
import json
from pathlib import Path
import pytest
from data_acquisition_agent.sql_judge.l1 import l1_check


# R5-C1: 用 __file__ 锚定 fixture 路径，避免 cwd-dependent 失败
# （pytest 从子目录或 VS Code Run Test 启动时 Path('tests/...') 会找不到文件）
_FIXTURE_PATH = Path(__file__).resolve().parent.parent / "sql_judge_fixtures" / "ddl_samples.json"


@pytest.fixture(scope="module")
def ddl_samples():
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def test_l1_blocks_all_ddl(ddl_samples):
    """L1 必须拦下 100% DDL"""
    failed = []
    for s in ddl_samples:
        result = l1_check(s["sql"])
        is_blocked = result["verdict"] == "block"
        if is_blocked != s["expected_block"]:
            failed.append({"sql": s["sql"], "got": is_blocked, "expected": s["expected_block"]})
    assert not failed, f"L1 误判 {len(failed)} 条:\n{failed}"


def test_l1_allows_safe_select():
    result = l1_check("SELECT user_id, name FROM users WHERE id = 123 LIMIT 10")
    assert result["verdict"] == "allow"


def test_l1_warns_select_star_with_limit():
    result = l1_check("SELECT * FROM users LIMIT 100")
    assert result["verdict"] == "warn"
    assert any("LIMIT" in w for w in result["warnings"])
```
**验证**:
```powershell
python -m pytest tests/data_acquisition_agent/sql_judge/test_l1.py -v
```
**预期**: 全过，特别是 `test_l1_blocks_all_ddl` 0 误判。

### Phase 1 commit
```powershell
git add data_acquisition_agent/sql_judge/__init__.py data_acquisition_agent/sql_judge/rules.py data_acquisition_agent/sql_judge/ast_analyzer.py data_acquisition_agent/sql_judge/l1.py tests/data_acquisition_agent/sql_judge/test_l1.py
git commit -m "feat(08): phase 1 L1 rule engine + 100% DDL coverage"
```

---

## Phase 2 — L2 LLM 审查

### Task 2.1 实现 Pydantic 输出 schema（Pydantic v2）
**Create**: `data_acquisition_agent/sql_judge/schemas.py`
**完整代码**:
```python
"""L2 review result schema (Plan 08 Phase 2). Pydantic v2."""
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal, Optional


class L2ReviewResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pass_: bool = Field(alias="pass")
    severity: Literal["low", "medium", "high"]
    suggestion: Optional[str] = None
    reasoning: str
```

> ⚠️ **调用约定**（R7-N1 准确修订）：LLM/Mock/测试三处统一用 `L2ReviewResult.model_validate(data)`。`L2ReviewResult(**data)` 在运行时**不会** SyntaxError（`**dict_unpack` 允许任意 string key 包括 Python 关键字），但混用 `(**data)` 与 `model_validate(data)` 容易造成 alias / 字段名 / kwargs 三套语义混乱。统一 v2 入口点 = 单一调用风格、未来 alias 调整时无需 audit `**` 散落点。

**验证命令**：
```powershell
python -c "from data_acquisition_agent.sql_judge.schemas import L2ReviewResult; r = L2ReviewResult.model_validate({'pass': True, 'severity': 'low', 'suggestion': None, 'reasoning': 'ok'}); print(r.pass_, r.model_dump(by_alias=True))"
```
**预期**：`True {'pass': True, 'severity': 'low', 'suggestion': None, 'reasoning': 'ok'}`

### Task 2.2 实现 L2 LLM 审查
**Create**: `data_acquisition_agent/sql_judge/llm_reviewer.py`
**完整代码**（必须经 `ModelClient.generate_structured`，route_key 与 config.yaml 一致使用点号）:
```python
"""L2 LLM-based SQL review (Plan 08 Phase 2). 调用必经 ModelClient.generate_structured。"""
from typing import Any
from app.core.model_client import ModelClient
from .schemas import L2ReviewResult


L2_REVIEW_PROMPT = """你是一个 SQL 代码审查专家。请审查以下 SQL，判断是否应该通过。

## 数据库 Schema
{schema}

## 历史成功示例（参考风格）
{few_shot_examples}

## 用户原始需求
{nl_query}

## 待审查的 SQL
```sql
{sql}
```

## L1 已发现的警告
{l1_warnings}

## 审查标准
1. 语义正确性：SQL 是否正确表达用户需求？
2. 字段正确性：引用的字段名是否在 schema 中存在？
3. 性能合理性：是否有明显性能问题？
4. 数据安全：是否暴露敏感字段（密码/token/手机号明文）？
5. 业务规则：是否符合业务约定？

## 输出格式（严格 JSON，键名以下 4 个无多余）
{{
  "pass": true | false,
  "severity": "low" | "medium" | "high",
  "suggestion": "如果 pass=false给出具体修复建议；否则为 null",
  "reasoning": "判断理由，不超过 200 字"
}}
"""


# 供 ModelClient 可选传入的 JSON Schema（provider 会作 response_schema 强制）
L2_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pass": {"type": "boolean"},
        "severity": {"type": "string", "enum": ["low", "medium", "high"]},
        "suggestion": {"type": ["string", "null"]},
        "reasoning": {"type": "string"},
    },
    "required": ["pass", "severity", "reasoning"],
}


def l2_review(
    sql: str,
    schema: str,
    nl_query: str,
    l1_warnings: list[str],
    few_shot_examples: str = "",
    client: ModelClient | None = None,
) -> L2ReviewResult:
    """调 LLM 结构化审查。

    R7-M1 修复：fallback 改为 fail-closed（pass=False, severity=high），
    LLM 不可用 / parse 失败时让反思循环走 reject → 3 轮后 failed_to_human →
    wrapper 保留 baseline_response 不动 → 走人工 ACK 预览。原 fail-open 
    （pass=True severity=high）会让 LLM 不可用时 SQL 静默通过 judge，与 §6.1 推荐 B 矛盾。
    """
    client = client or ModelClient()
    prompt = L2_REVIEW_PROMPT.format(
        schema=schema,
        few_shot_examples=few_shot_examples or "（无）",
        nl_query=nl_query,
        sql=sql,
        l1_warnings="\n".join(f"- {w}" for w in l1_warnings) or "（无）",
    )
    fallback_data = {
        "pass": False, "severity": "high",
        "suggestion": None, "reasoning": "LLM unavailable, default-deny route to human",
    }
    result = client.generate_structured(
        skill_name="sql_judge_l2",
        prompt=prompt,
        fallback_result=fallback_data,
        response_schema=L2_RESPONSE_SCHEMA,
        route_key="sql_judge.l2",   # 必须与 config.yaml routes 一致（点号风格）
    )
    # status 可能是 "ok" 或 "model_unavailable"。两者 structured_result 都是 dict，可直接 model_validate
    payload: dict[str, Any] = result.get("structured_result") or fallback_data
    try:
        return L2ReviewResult.model_validate(payload)
    except Exception as e:
        return L2ReviewResult.model_validate({
            "pass": False, "severity": "high",
            "suggestion": None, "reasoning": f"LLM 输出解析失败: {e}",
        })
```

> **关键点**：
> 1. **不调 `client.generate(...)`**— ModelClient 只有 `generate_structured(...)`（已验证）
> 2. `route_key="sql_judge.l2"` 点号与 Task 2.3 + config.yaml routes 点号一致 — 不能一处用下划线一处用点号
> 3. `fallback_result` 是 CLAUDE.md Zero Tolerance 必传参数（支持 mock 降级）
> 4. `response_schema` 走 ModelClient 现有 JSON Schema 强制机制，减少输出解析失败

### Task 2.3 config.yaml 添加 sql_judge.l2 路由
**Modify**: `config.yaml`
**追加（在 `llm.routes` 下）**:
```yaml
routes:
  # ... 上面已有的 9 条 ...
  sql_judge.l2: gemini   # 与其他 9 条 route 点号风格一致；Maestro Spike 后可反转为 claude_maestro
```

> 不新增 `gemini_flash` provider。现有 `gemini` provider 已是 `gemini-2.5-flash` 模型，避免增加另一个名字混乱。
> **必须使用点号（`sql_judge.l2`）与 Task 2.2 代码中 `route_key` 严格一致** — `app/core/config.py::llm_provider_for(route_key)` 是完全字符串匹配，下划线会造成路由 miss。

**验证命令**：
```powershell
python -c "from app.core.config import llm_provider_for; print(llm_provider_for('sql_judge.l2'))"
```
**预期**：`gemini`

### Task 2.4 unit test（mock LLM）
**Create**: `tests/data_acquisition_agent/sql_judge/test_llm_reviewer.py`
**完整代码**（mock `ModelClient.generate_structured` 返回`{"status":"ok","structured_result":{...}}` 结构）:
```python
from unittest.mock import MagicMock
from data_acquisition_agent.sql_judge.llm_reviewer import l2_review
from data_acquisition_agent.sql_judge.schemas import L2ReviewResult


def _mock_client_returning(structured_result: dict) -> MagicMock:
    """返回一个 mock ModelClient，generate_structured 返回指定 structured_result."""
    client = MagicMock()
    client.generate_structured.return_value = {
        "status": "ok",
        "structured_result": structured_result,
        "model_name": "mock", "prompt_preview": "",
    }
    return client


def test_l2_pass():
    client = _mock_client_returning({
        "pass": True, "severity": "low",
        "suggestion": None, "reasoning": "looks good",
    })
    result = l2_review("SELECT 1", "schema", "test", [], client=client)
    assert isinstance(result, L2ReviewResult)
    assert result.pass_ is True
    # 验证 ModelClient 被以正确参数调用（route_key 点号）
    kwargs = client.generate_structured.call_args.kwargs
    assert kwargs["route_key"] == "sql_judge.l2"
    assert kwargs["skill_name"] == "sql_judge_l2"
    assert "fallback_result" in kwargs
    assert "response_schema" in kwargs


def test_l2_fail_with_suggestion():
    client = _mock_client_returning({
        "pass": False, "severity": "high",
        "suggestion": "add WHERE", "reasoning": "missing where",
    })
    result = l2_review("SELECT 1", "schema", "test", [], client=client)
    assert result.pass_ is False
    assert result.suggestion == "add WHERE"


def test_l2_handles_model_unavailable():
    """R7-M1 fail-closed 求证：当 ModelClient 返 status==model_unavailable 时，
    structured_result == fallback_result（pass=False, severity=high）。
    l2_review 不报错且默认 deny，与 Spec §6.1 fail-closed 决策一致。"""
    client = MagicMock()
    client.generate_structured.return_value = {
        "status": "model_unavailable",
        "structured_result": {
            "pass": False, "severity": "high",
            "suggestion": None, "reasoning": "LLM unavailable, default-deny route to human",
        },
        "model_name": "mock", "prompt_preview": "",
    }
    result = l2_review("SELECT 1", "schema", "test", [], client=client)
    # R7-M1 fail-closed：LLM 不可用 → 默认 reject → 走反思循环 3 轮 →
    # failed_to_human → wrapper 保留 baseline_response → 人工 ACK。
    assert result.pass_ is False
    assert result.severity == "high"
    assert "unavailable" in result.reasoning.lower()
```

**验证**：
```powershell
python -m pytest tests/data_acquisition_agent/sql_judge/test_llm_reviewer.py -v
```
**预期**：3 passed。

### Phase 2 commit
```powershell
git add data_acquisition_agent/sql_judge/llm_reviewer.py data_acquisition_agent/sql_judge/schemas.py config.yaml tests/data_acquisition_agent/sql_judge/test_llm_reviewer.py
git commit -m "feat(08): phase 2 L2 LLM reviewer + pydantic schema + sql_judge.l2 route"
```

---

## Phase 3 — 反思循环

### Task 3.1 实现 reflection loop
**Create**: `data_acquisition_agent/sql_judge/loop.py`
**完整代码**:
```python
"""SQLGen <-> Judge reflection loop (Plan 08 Phase 3)."""
from typing import Callable
from .l1 import l1_check
from .llm_reviewer import l2_review

MAX_ROUNDS = 3


def reflective_sql_gen(
    nl_query: str,
    country: str,
    schema: str,
    sql_gen_fn: Callable[[str, str, str | None], str],
    few_shot_examples: str = "",
) -> dict:
    """
    sql_gen_fn 签名: (nl_query, country, feedback) -> sql_str
    """
    history = []
    feedback: str | None = None
    last_sql = None

    for round_idx in range(1, MAX_ROUNDS + 1):
        sql = sql_gen_fn(nl_query, country, feedback)

        # 重复 SQL 检测：连续两轮一样 → 提前退出
        if sql == last_sql:
            history.append({"round": round_idx, "sql": sql, "l1": None, "l2": None,
                           "note": "duplicate sql, abort"})
            break
        last_sql = sql

        l1_result = l1_check(sql)
        round_record = {"round": round_idx, "sql": sql, "l1": dict(l1_result), "l2": None}

        if l1_result["verdict"] == "block":
            feedback = f"L1 拒绝：{l1_result['reason']}"
            history.append(round_record)
            continue

        l2_result = l2_review(sql, schema, nl_query, l1_result["warnings"], few_shot_examples)
        round_record["l2"] = l2_result.model_dump(by_alias=True)
        history.append(round_record)

        if l2_result.pass_:
            return {
                "final_sql": sql,
                "rounds": round_idx,
                "verdict": "passed",
                "history": history,
            }

        feedback = f"L2 拒绝（severity={l2_result.severity}）：{l2_result.suggestion}"

    return {
        "final_sql": history[-1]["sql"] if history else "",
        "rounds": len(history),
        "verdict": "failed_to_human",
        "history": history,
    }
```

### Task 3.2 unit test
**Create**: `tests/data_acquisition_agent/sql_judge/test_loop.py`
**完整代码**（全部用 `model_validate` 避开 Python 关键字陷阱）:
```python
from unittest.mock import patch
from data_acquisition_agent.sql_judge.loop import reflective_sql_gen
from data_acquisition_agent.sql_judge.schemas import L2ReviewResult


def _l2_pass() -> L2ReviewResult:
    return L2ReviewResult.model_validate({
        "pass": True, "severity": "low", "suggestion": None, "reasoning": "ok",
    })


def test_passes_on_first_round():
    """L1 + L2 都通过 → 一轮搞定"""
    sql_gen = lambda q, c, fb: "SELECT user_id FROM users WHERE id=1 LIMIT 10"
    with patch("data_acquisition_agent.sql_judge.loop.l2_review") as mock_l2:
        mock_l2.return_value = _l2_pass()
        result = reflective_sql_gen(
            nl_query="test", country="mexico", schema="schema", sql_gen_fn=sql_gen,
        )
    assert result["verdict"] == "passed"
    assert result["rounds"] == 1


def test_reflects_on_l1_block():
    """第一轮 DROP，第二轮改对"""
    sqls = iter(["DROP TABLE users", "SELECT user_id FROM users WHERE id=1 LIMIT 10"])
    sql_gen = lambda q, c, fb: next(sqls)
    with patch("data_acquisition_agent.sql_judge.loop.l2_review") as mock_l2:
        mock_l2.return_value = _l2_pass()
        result = reflective_sql_gen(
            nl_query="test", country="mexico", schema="schema", sql_gen_fn=sql_gen,
        )
    assert result["verdict"] == "passed"
    assert result["rounds"] == 2


def test_fails_to_human_after_3_rounds():
    """R5-M1: 3 轮输出都被 L1 block 但每轮 SQL 不同（避开 dup 检测） → 真正耗尽 MAX_ROUNDS=3 → 走人审"""
    sqls = iter(["DROP TABLE u1", "DROP TABLE u2", "DROP TABLE u3"])
    sql_gen = lambda q, c, fb: next(sqls)
    result = reflective_sql_gen(
        nl_query="test", country="mexico", schema="schema", sql_gen_fn=sql_gen,
    )
    assert result["verdict"] == "failed_to_human"
    assert result["rounds"] == 3, f"Expected MAX_ROUNDS exhausted, got rounds={result['rounds']}"


def test_duplicate_sql_aborts_early():
    """L1 block 且连续两轮输出同样 SQL → 提前退出（防 Agent 卡死，与上一个 test 互补）"""
    sql_gen = lambda q, c, fb: "DROP TABLE users"
    result = reflective_sql_gen(
        nl_query="test", country="mexico", schema="schema", sql_gen_fn=sql_gen,
    )
    assert result["verdict"] == "failed_to_human"
    # dup 检测会在第 2 轮提前 break（rounds < MAX_ROUNDS=3），与上一个 test 形成对照
    assert result["rounds"] < 3
```

**验证**：
```powershell
python -m pytest tests/data_acquisition_agent/sql_judge/test_loop.py -v
```
**预期**：4 passed。

### Phase 3 commit
```powershell
git add data_acquisition_agent/sql_judge/loop.py tests/data_acquisition_agent/sql_judge/test_loop.py
git commit -m "feat(08): phase 3 reflection loop with max 3 rounds + dup-sql abort"
```

---

## Phase 4 — Sidecar Wrapper 集成 + 验收 + [complete]

### Task 4.1 实现 Sidecar Wrapper（不动 orchestrator.py，返回类型仍是 GenerateResponse）
**Create**: `data_acquisition_agent/sql_judge/wrapper.py`（新文件，不侵入 11 个核心 .py）
**完整代码**（与 Spec § 4.3 严格一致，**返回类型 = `GenerateResponse`**，feedback 注入 = 拼接到 `natural_language_request`，不改原 orchestrator 签名）:
```python
"""Sidecar wrapper: 包装 DataAcquisitionOrchestrator，不侵入 164 tests 锁定区。
返回类型与原 orchestrator 一致 = GenerateResponse。"""
import os
from pathlib import Path
from data_acquisition_agent.orchestrator import DataAcquisitionOrchestrator
from data_acquisition_agent.schemas import GenerateRequest, GenerateResponse
from data_acquisition_agent.sql_judge.loop import reflective_sql_gen


class JudgedDataAcquisitionOrchestrator:
    def __init__(self) -> None:
        self._inner = DataAcquisitionOrchestrator()

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        # 1. 先调原 orchestrator。返回的 baseline_response 是 Pydantic GenerateResponse 实例。
        baseline_response = self._inner.generate(request)

        # 2. SQL_JUDGE_ENABLED=0 → 兑底：原费返回
        if os.getenv("SQL_JUDGE_ENABLED", "1") == "0":
            return baseline_response
        # 3. baseline 未生成 sql（python-only / 报错）→ judge 无从介入。原费返回
        if not baseline_response.sql:
            return baseline_response
        # 4. R7-M2: V1 scope = query_only / EXTRACT only。
        # build_table_script artifact 含 CREATE/DROP/ALTER 是 intended 行为，
        # L1 黑名单会全部 block。这类 artifact 直接走人工 ACK，不经 judge。
        if baseline_response.sql_kind == "build_table_script":
            return baseline_response

        # 5. 反思循环。feedback 拼接到 natural_language_request，不改原 orchestrator 签名。
        original_nl = request.natural_language_request
        country_str = request.target_country.value

        def sql_gen_fn(nl_query: str, country: str, feedback: str | None) -> str:
            if feedback is None:
                return baseline_response.sql
            judged_request = request.model_copy(update={
                "natural_language_request": (
                    f"上轮生成的 SQL 有问题，请根据以下反馈重新生成：\n{feedback}\n\n"
                    f"原始需求：\n{original_nl}"
                ),
            })
            new_resp = self._inner.generate(judged_request)
            return new_resp.sql or ""

        schema_text = self._load_schema_for_judge(country_str)

        judge_result = reflective_sql_gen(
            nl_query=original_nl,
            country=country_str,
            schema=schema_text,
            sql_gen_fn=sql_gen_fn,
        )

        # 6. R7-H2 修复：failed_to_human 时 final_sql 是最后一次被 L1/L2 reject 的 SQL，
        # 比 baseline 还危险，绝不能静默回写。保留 baseline_response 不变，让人工 ACK
        # 路径（agent_loop.py 仍要用户确认）处理原 baseline。只有 verdict=="passed" 才合并。
        if judge_result["verdict"] != "passed":
            return baseline_response

        return baseline_response.model_copy(update={
            "sql": judge_result["final_sql"],   # passed 路径必有 final_sql，无 None 兜底必要
        })

    @staticmethod
    def _load_schema_for_judge(country: str) -> str:
        """V1 stub：依次尝试 `<country>.local.yaml` → `<country>.yaml`。
        路径验证 (2026-05)：`data_acquisition_agent/configs/` 下存在
        `mexico.local.yaml` / `mexico.yaml` / `thailand.yaml` / `indonesia.yaml` /
        `pakistan.yaml` / `philippines.yaml`。**V1 仅 mx + th 在范围内**且能命中
        `<country>.yaml`；其余 3 国（indonesia / pakistan / philippines）暂不在 V1 范围，
        但 fallback 链保留作为未来扩展接口（indonesia.yaml 是空 placeholder，会返回
        几行注释；pk / ph yaml 已填）。Plan 07 完成后可改为 knowledge_base 路由后精简版。"""
        cfg_dir = Path(__file__).resolve().parents[1] / "configs"
        candidates = [
            cfg_dir / f"{country}.local.yaml",   # mx 优先
            cfg_dir / f"{country}.yaml",          # V1 mx + th 命中；其余 3 国未来扩展
        ]
        for p in candidates:
            if p.exists():
                return p.read_text(encoding="utf-8")
        return "(schema unavailable)"
```

**关键点**（面试点）：
1. **返回类型 = GenerateResponse**。调用方 [tools/query_data.py](app/services/orchestrator_agent/tools/query_data.py) `gen_resp.sql or ""` 表达式零改动。
2. **feedback 注入 = 拼 NL**，不改原 `generate(request: GenerateRequest)` 签名（Surgical Hard Boundary）。
3. **凭据扫描不重复**：`baseline_response = self._inner.generate(request)` 已走过 `_enforce_output_policies`。
4. **三类跳过 judge 的 short-circuit**：(a) `SQL_JUDGE_ENABLED=0` 开关；(b) `baseline_response.sql is None`（python-only / orchestrator 报错）；(c) **R7-M2: `baseline_response.sql_kind == "build_table_script"`（V1 scope = query_only/EXTRACT only，build_table 走人审）**。
5. **R7-H2: failed_to_human 不静默回写**。`judge_result["verdict"] != "passed"` 时保留 baseline_response 不变，**禁止**用最后一轮 reject 的 SQL 覆盖原 SQL（否则更危险）。仅 verdict=="passed" 才合并 corrected `final_sql`。

**验证命令**（不依赖 LLM 实调，仅验证语义导入不报错）:
```powershell
python -c "from data_acquisition_agent.sql_judge.wrapper import JudgedDataAcquisitionOrchestrator; w = JudgedDataAcquisitionOrchestrator(); print(type(w._inner).__name__)"
```
**预期**：`DataAcquisitionOrchestrator`。

### Task 4.2 切换调用（import 行 + 实例化行，合计 2 处）
**Modify**: `app/services/orchestrator_agent/tools/query_data.py`（该文件不在 164 tests 锁定区；L8 docstring 「不动 data_acquisition_agent 任何文件」 — 本 Plan 不违反，仅修改该文件本身）
**改动幾处**：**2 行**（import + 实例化），不是「仅 1 行」。

**完整 diff**：
```python
# L17 现状
from data_acquisition_agent.orchestrator import DataAcquisitionOrchestrator
# L17 改为
from data_acquisition_agent.sql_judge.wrapper import JudgedDataAcquisitionOrchestrator

# L54 现状
self._orch = DataAcquisitionOrchestrator()
# L54 改为
self._orch = JudgedDataAcquisitionOrchestrator()
```

> ⚠️ 实际行号以 Phase 0 Task 0.1 核实为准。Phase 0 核实明确记录了「import 位于 L17、实例化位于 L54」两处。

**验证命令**：
```powershell
Get-Content app/services/orchestrator_agent/tools/query_data.py | Select-String "DataAcquisitionOrchestrator|JudgedDataAcquisitionOrchestrator"
```
**预期**：原 `DataAcquisitionOrchestrator` 0 次出现（全部替换），`JudgedDataAcquisitionOrchestrator` 出现 2 次（import + 实例化）。

### Task 4.3 跑 164 tests 验证仍绿
```powershell
python -m pytest data_acquisition_agent/tests/ -v 2>&1 | Select-String "passed|failed" | Select-Object -Last 3
```
**预期**：164 passed (1 skipped)，**与 Phase 0 Task 0.1 记录的基线完全一致**。这证明原 orchestrator 未被侵入，wrapper 在外面叠加逻辑不影响原德。

### Task 4.4 跑全量回归（含 query_data 调用链）
```powershell
python -m pytest tests/ data_acquisition_agent/tests/ -v 2>&1 | Select-String "passed|failed" | Select-Object -Last 3
```
**预期**：
- `data_acquisition_agent/tests/` 仍是 164 passed (1 skipped)
- `tests/` 原有数字 + sql_judge 新增 tests（L1 + L2 + loop + wrapper smoke + happy path off）
- `tests/test_orchestrator_*.py`（包含 `test_orchestrator_golden.py` query_data 路径、`test_orchestrator_phase1.py`゜`phase3.py`、`test_orchestrator_chat_routes.py`，实验证 7 个文件都在）仍绿。
  query_data 包装后调用返回类型仍是 GenerateResponse，零行为变动。
  ⚠️ 仓库当前**不存在** `tests/test_query_data*.py`（R4-C1 验证）；如后续新增此名字的专项测试需同步补入本表。

### ~~（已删除任务）~~ 可疑 SELECT * 拦截测试 → 推到 Plan 09

> **R6-M1 修复**：原本占用 Task 4.5 编号，但实测是 tautology（mock 返回值从 `expected_l2_block` 反推、再用该返回值对比 `expected_l2_block` → 100% 永远 pass，零信号）。Round 2 审核发现后推迟到 Plan 09 评测集 + 真实 gemini-flash 调用。**本节保留为 audit trail（解释为什么没有 SELECT * 拦截率单测），不占用 Task 编号**，避免与下面真正的 Task 4.5 冲突。
>
> 不创建 `tests/data_acquisition_agent/sql_judge_fixtures/suspicious_select_star.json`，不创建 `test_select_star_block_rate.py`。Plan 09 ready 后重新以评测集形式补上。

### Task 4.5 验收：L2 prompt 在 V1 双国都能加载到非空 schema

**背景**（C2/C3 修复后的验收项）：`_load_schema_for_judge` 已从 `demo0/business_logic.md`（不存在）改为 `<country>.local.yaml → <country>.yaml` 两级 fallback。本 Task 验证 **V1 范围内的 mx + th 双国**都能命中 + 未知国家走哨兵。其余 3 国（indonesia / pakistan / philippines）当前不在 V1 范围内，fallback 链保留作为未来扩展接口但不做 V1 测试断言。

**Create**: `tests/data_acquisition_agent/sql_judge/test_schema_loader.py`
**完整代码**：
```python
"""C2/C3 修复后的 schema fallback 验收：V1 双国（mx + th）都能拿到非空 schema。

V1 范围：仅 mexico + thailand。其余 3 国（indonesia / pakistan / philippines）当前
不在 V1 范围（用户决策 2026-05-06），fallback 链保留作为未来扩展接口但不做断言。
未来扩展时只需把对应 test 函数加回来即可（pk / ph yaml 已填，加测试即过；indonesia.yaml
当前是空 placeholder，需先补 yaml 字段才能加测试）。
"""
from data_acquisition_agent.sql_judge.wrapper import JudgedDataAcquisitionOrchestrator


class _T:
    """外露 _load_schema_for_judge 静态方法调用。"""
    load = staticmethod(JudgedDataAcquisitionOrchestrator._load_schema_for_judge)


def test_mexico_loads_local_yaml_first():
    schema = _T.load("mexico")
    assert schema and schema != "(schema unavailable)"
    assert len(schema) > 50


def test_thailand_falls_back_to_yaml():
    schema = _T.load("thailand")
    assert schema and schema != "(schema unavailable)"


def test_unknown_country_returns_sentinel():
    """未知国家 → 返回哨兵字符串，不报错。"""
    assert _T.load("atlantis") == "(schema unavailable)"
```

**验证**：
```powershell
python -m pytest tests/data_acquisition_agent/sql_judge/test_schema_loader.py -v
```
**预期**：3 passed。这证明 wrapper 在 V1 双国都能加载到真 schema、未知国走哨兵 — L2 prompt 不会留下 `(schema unavailable)` 空洞。

### Task 4.6 兜底人审路径 + 安全分支自动化验证（SQL_JUDGE_ENABLED=0 + R7-H2 failed_to_human + R7-M2 build_table_script）
**Create**: `tests/data_acquisition_agent/sql_judge/test_kill_switch.py`
**完整代码**：
```python
"""Wrapper safety tests:
- SQL_JUDGE_ENABLED=0 → 走原 orchestrator
- baseline_response.sql is None → judge 不介入
- R7-M2: build_table_script artifact → 跳过 judge
- R7-H2: failed_to_human 不静默回写最后一轮 reject 的 SQL
"""
from unittest.mock import MagicMock, patch
from data_acquisition_agent.sql_judge.wrapper import JudgedDataAcquisitionOrchestrator
from data_acquisition_agent.schemas import GenerateRequest, GenerateResponse, TargetCountry


def test_kill_switch_returns_baseline(monkeypatch):
    """SQL_JUDGE_ENABLED=0 → wrapper.generate 直接返回 _inner.generate 结果（同一引用）"""
    monkeypatch.setenv("SQL_JUDGE_ENABLED", "0")
    w = JudgedDataAcquisitionOrchestrator()
    fake_resp = MagicMock(spec=GenerateResponse)
    fake_resp.sql = "SELECT 1"
    w._inner = MagicMock()
    w._inner.generate.return_value = fake_resp

    req = MagicMock(spec=GenerateRequest)
    out = w.generate(req)
    assert out is fake_resp
    w._inner.generate.assert_called_once_with(req)


def test_no_sql_returns_baseline(monkeypatch):
    """baseline_response.sql is None → judge 不介入，原费返回。"""
    monkeypatch.setenv("SQL_JUDGE_ENABLED", "1")
    w = JudgedDataAcquisitionOrchestrator()
    fake_resp = MagicMock(spec=GenerateResponse)
    fake_resp.sql = None
    w._inner = MagicMock()
    w._inner.generate.return_value = fake_resp

    req = MagicMock(spec=GenerateRequest)
    out = w.generate(req)
    assert out is fake_resp
    w._inner.generate.assert_called_once_with(req)


def test_build_table_script_skips_judge(monkeypatch):
    """R7-M2: V1 scope = query_only / EXTRACT only。build_table_script 跳过 judge。"""
    monkeypatch.setenv("SQL_JUDGE_ENABLED", "1")
    w = JudgedDataAcquisitionOrchestrator()
    fake_resp = MagicMock(spec=GenerateResponse)
    fake_resp.sql = "CREATE TABLE analyst.tmp_x AS SELECT * FROM users"
    fake_resp.sql_kind = "build_table_script"
    w._inner = MagicMock()
    w._inner.generate.return_value = fake_resp

    req = MagicMock(spec=GenerateRequest)
    out = w.generate(req)
    # judge 被跳过：_inner.generate 仅调一次（baseline），不进反思循环
    assert out is fake_resp
    assert w._inner.generate.call_count == 1


def test_failed_to_human_does_not_silent_overwrite(monkeypatch):
    """R7-H2: judge 3 轮失败时，wrapper 必须保留 baseline，不能用最后一轮 reject 的 SQL 覆盖。"""
    monkeypatch.setenv("SQL_JUDGE_ENABLED", "1")
    w = JudgedDataAcquisitionOrchestrator()
    fake_baseline = MagicMock(spec=GenerateResponse)
    fake_baseline.sql = "SELECT user_id FROM users WHERE id=1 LIMIT 10"   # 安全 baseline
    fake_baseline.sql_kind = "query_only"
    w._inner = MagicMock()
    w._inner.generate.return_value = fake_baseline

    judge_failed = {
        "verdict": "failed_to_human",
        "rounds": 3,
        "final_sql": "DROP TABLE users",   # 最后一轮 reject 的危险 SQL
        "history": [],
    }
    req = MagicMock(spec=GenerateRequest)
    req.natural_language_request = "test"
    req.target_country = TargetCountry.MEXICO

    with patch("data_acquisition_agent.sql_judge.wrapper.reflective_sql_gen", return_value=judge_failed):
        out = w.generate(req)

    # wrapper 必须返回原 baseline 引用，而不是被 final_sql=DROP TABLE 污染的 model_copy
    assert out is fake_baseline, "failed_to_human 时 wrapper 不能静默用 final_sql 覆盖 baseline_response.sql"
```

**验证**：
```powershell
python -m pytest tests/data_acquisition_agent/sql_judge/test_kill_switch.py -v
```
**预期**：4 passed（kill_switch + no_sql + R7-M2 build_table_script_skips + R7-H2 failed_to_human_no_overwrite）。

### Task 4.7 Phase 4 stage + commit（C1 修复：不能用 `--allow-empty`，必须反过来先 stage 再 commit）
```powershell
# C1 修复：Phase 4 创建了 wrapper.py / test_kill_switch.py / test_schema_loader.py
# + 修改了 query_data.py。所有改动必须进一次非空 commit。
git add data_acquisition_agent/sql_judge/wrapper.py app/services/orchestrator_agent/tools/query_data.py tests/data_acquisition_agent/sql_judge/test_kill_switch.py tests/data_acquisition_agent/sql_judge/test_schema_loader.py
git status --short   # 人工核实 stage 列表与 Phase 4 预期一致（3 新 + 1 改）
git commit -m "feat(08): phase 4 sidecar wrapper + kill switch + multi-country schema fallback"
```
**验证**：`git log --oneline -1` 必须是 Phase 4 commit不是空。

### Task 4.8 [complete] marker + push
```powershell
git remote -v | findstr origin   # 必须先验证 origin 指向 lizheng33193/CHORD（或当前批准仓库）
git commit --allow-empty -m "[complete] plan-08 — sql judge as sidecar wrapper"
git push origin main
```
> 用户偏好（最高优先级）：仅推当前批准仓库对应的 remote；当前仓库默认使用 `origin`。

---

## 五点检查法（自审，Round 2 后重新评估）

| # | 检查项 | 状态 |
|---|---|---|
| 1 | 精确文件路径 | ✅ 含 Sidecar 位置（§ 0.2）+ schema fallback 路径 × 2（C2/C3 修复后）+ query_data.py L17/L54 |
| 2 | 无占位符 | ✅ ddl_samples.json **50 条全量 enumeration**（M1 修复）；sidecar wrapper 完整代码在 Task 4.1 |
| 3 | 完整代码块 | ✅ L1/L2/loop/wrapper/kill_switch/schema_loader 全给出；mock LLM tautology 测试已删（C4 修复） |
| 4 | 验证命令 + 预期 | ✅ 含 sqlglot AST 节点验证 / V1 双国 schema fallback (mx + th + unknown sentinel) / SQL_JUDGE_ENABLED=0 happy path / Phase 4 stage 人工核实 |
| 5 | 一个不熟悉项目的人能独立执行完 | ✅ wrapper 签名/返回类型/feedback 注入/2 行调用方修改/Phase 4 stage+commit 均明确（C1 修复） |

---

## 回滚预案

```powershell
$env:SQL_JUDGE_ENABLED="0"   # 立即关闭 judge
```

无效则 `git reset --hard {baseline_commit}`。

---

## 风险登记

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 反思循环死循环 | 中 | 中 | MAX_ROUNDS=3 + 重复 SQL 检测（loop.py 已实现） |
| L2 LLM hallucination 说 pass 但有问题 | 中 | 高 | L1 已拦结构问题；Plan 09 评测兑底 |
| sqlglot 不支持 StarRocks 特殊语法 | 低 | 中 | parse 失败 → ast_analyzer 返回 `(False, [“SQL 语法错误”])`（保守，L1 block）；**不**静默降级为纯正则。Spec § 8.2 与本表一致 |
| L2 latency 累加 | 中 | 低 | gemini-flash 单次 < 500ms |
| Sidecar 物理位置与 Surgical Hard Boundary 理解分歧 | 中 | 中 | **R7-H1 修复**：从「默认 A，用户不推翻即生效」升级为 Phase 0 Task 0.0 `STOP-AND-CONFIRM` 显式确认门，未拍板不进 Task 0.1 |
| query_data.py 调用方报 AttributeError（返回类型变） | 低 | 高 | wrapper 返回类型仍是 GenerateResponse（与原 orchestrator 一致）；Task 4.4 跑 `tests/test_orchestrator_*.py`（含 `test_orchestrator_golden.py` query_data 路径，已验证存在）验证。仓库当前**不存在** `test_query_data*.py`（R4-C1） |
| **多国场景 schema 不可用**（C2/C3 Round 2 发现） | 低 | 高 | C2/C3 修复后 fallback = `<country>.local.yaml → <country>.yaml`；Task 4.5 `test_schema_loader.py` 3 例验收 V1 双国 (mx + th) + unknown sentinel；3 国 (id/pk/ph) 当前不在 V1 范围，fallback 链保留作为未来扩展接口 |
| **Phase 4 commit 漏提新文件**（C1 Round 2 发现） | 已连 | 高 | Task 4.7 从 `--allow-empty` 拆为 Stage+commit + [complete] marker 两步 |
| **R7-H2: judge failed_to_human 静默回写危险 SQL** | 中 | 高 | wrapper 加 `if judge_result['verdict'] != 'passed': return baseline_response` 分支；Task 4.6 `test_failed_to_human_does_not_silent_overwrite` 验收 |
| **R7-M2: build_table_script artifact 被 L1 全部 block**（V1 scope 不清致全部死锁） | 中 | 高 | V1 scope 收紧 = query_only/EXTRACT only；wrapper 加 `if baseline_response.sql_kind == 'build_table_script': return baseline_response` 跳过；Task 4.6 `test_build_table_script_skips_judge` 验收；fixture 12 行 DML 全 block，与 `output_scanner.py` 对齐 |
| **R7-M1: LLM unavailable 时 fallback fail-open** | 低 | 中 | `l2_review` fallback 改 `pass=False, severity=high`（fail-closed）：LLM 不可用 → 反思 3 轮 → failed_to_human → 走 R7-H2 分支保留 baseline → 人工 ACK |

---

## 测试矩阵

| 类别 | 范围 | 触发 |
|---|---|---|
| L1 单元 | tests/data_acquisition_agent/sql_judge/test_l1.py（50 条 fixture，**R7-M2 后**：40 block + 10 allow） | Phase 1/4 |
| L2 单元（mock） | test_llm_reviewer.py | Phase 2/4 |
| 反思 loop | test_loop.py（含重复 SQL 提前退出） | Phase 3/4 |
| Wrapper happy path off + no-sql | test_kill_switch.py | Phase 4 |
| Schema fallback 多国验收 | test_schema_loader.py（C2/C3 修复验收） | Phase 4 |
| ~~SELECT * 拦截率」~~ | ~~test_select_star_block_rate.py~~ — **已删（C4 tautology）**推到 Plan 09 评测集 + 真实 LLM 验收 | — |
| 163 da-agent 回归 | data_acquisition_agent/tests/ | Phase 4 严格与基线一致 |
| 全量回归 | tests/ | Phase 4 |
| Plan 09 评测集 | run_eval --subset | Phase 4（如可用） |

---

## TASK.md 记一行

```markdown
- [ ] SQLJudge 反思循环 → docs/plans/08-sql-judge-plan.md
```
