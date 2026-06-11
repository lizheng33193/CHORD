# Design Doc 08 — SQLJudge（L1 规则 + L2 LLM + 反思循环）

> **STATUS**: ⚠️ DRAFT — 待用户审核后改为 `READY-FOR-PLAN`
> **作者**: Codex / Claude（自动生成草稿）
> **日期**: 2026-05-05
> **关联 Plan**: `docs/plans/08-sql-judge-plan.md`
> **依赖前置**: Plan 07 完成（knowledge_base 已上，schema 注入精简版可用）
> **关联文档**:
> - Harness Engineering 学习笔记 §10 Resilience 层（错误三板斧 + 反思循环）
> - Harness Engineering 学习笔记 §8 Security 层（命令级 + 工具级 + 审批级）
> - `data_acquisition_agent/orchestrator.py`（现有 ack 路径）
> - `CLAUDE.md` SQL/凭据安全 + data_acquisition_agent artifact 安全约束

---

## 0. 背景与目标

### 0.1 现状
- DataAcquisitionAgent 生成的 SQL **直接走人工 ack 路径**
- 已知质量问题：
  - 偶发 DDL 语句（DROP/TRUNCATE/ALTER）
  - 偶发全表扫（SELECT * 无 WHERE / 无 LIMIT）
  - 字段拼错（typo，运行时才发现）
  - 子查询嵌套过深（性能差但能跑）
- 人工 ack 是"最后一道防线"，但用户负担重

### 0.2 目标
- **SQL 通过率 > 95%**（一次性生成就过 audit 的比例）
- **反思循环 3 轮内成功率 ≥ 80%**（一次没过的，3 轮反思能补救）
- **L1 拦下 100% DDL/TRUNCATE 及显式全表扫描（`SELECT *` 同时缺 `WHERE` 与 `LIMIT`）**（Zero Tolerance）
- **L2 拦下 ≥ 80% “L1 放行但仍可疑”的 SELECT * 场景**（例如有 WHERE 不严、无 LIMIT；显式全表扫已被 L1 拦下，L2 负责“可疑但未明显违规”那层）

> ⚠️ **CLAUDE.md artifact 安全约束：即使 L1+L2 都通过，SQL 仍是待审核 artifact**。SQLJudge 只是“减少人工 ack 负担”，不是“取代人工 ack”。V2 `/execute` 入口仍必须提交 `approved_sql + approved_by` 字段。本 Plan 不修改 V2 入口补充逻辑。
>
> ⚠️ **凭据扫描已由原 orchestrator 完成**：`data_acquisition_agent/orchestrator.py::_enforce_output_policies` 调 `scan_credentials` 会抦截凭据泄露。Sidecar Wrapper 调 `self._inner.generate(request)` 拿到的 `baseline_response` 已走过该检查。本 Plan L1/L2 **不重复扫凭据**，仅看 SQL 结构/语义安全。

### 0.3 设计依据：Harness §10 错误三板斧 + §8 纵深防御

> §10：工具失败 → 包装为 ToolMessage 喂回 LLM 让自己修复；最大循环轮次防 Agent 卡死。
> §8：命令级（黑名单 + AST）→ 工具级（白名单 + 风险评分）→ 审批级（Smart Approval）。多层独立检查，互不信任。

本 Plan 把这两个思想结合：
- **L1 规则引擎** = §8 命令级（毫秒级，零成本，独立检查）
- **L2 LLM 审查** = §8 工具级 + 审批级（语义理解，看 schema 上下文）
- **反思循环** = §10 错误三板斧（L1/L2 失败 → 喂回 suggestion → SQLGen 修复，最多 3 轮）

---

## 1. 范围与非目标

### 1.1 ✅ 范围内
| 项 | 说明 |
|---|---|
| **V1 服务范围** （R7-M2 明确） | 仅 `query_data` / `TargetAction.EXTRACT` 路径。`build_table_script` artifact 含 CREATE/DROP/ALTER 是 intended 行为，不走 SQLJudge（走人审原路径，V2 单独设计）。Wrapper 内依 `baseline_response.sql_kind == "build_table_script"` 跳过 judge。 |
| L1 规则引擎 | 正则黑名单（V1 scope: 全部 DELETE/UPDATE/INSERT block，与 `output_scanner.py` query_only 政策严格对齐）+ sqlglot AST 静态分析 |
| L2 LLM 审查 | gemini-flash 调用，仅 L1 通过才调（成本控制） |
| SQLGen ↔ Judge 反思循环 | 最大 3 轮，**失败走人审保底（wrapper 保留 baseline_response 不动，不静默回写最后一轮 reject 的 SQL）**。R7-H2 修复 |
| 集成到 DataAcq orchestrator | ack 前插入 judge 步骤（SQLJudge passed 后 → 进入人工 ACK 预览，**不**是自动 ack） |
| Hook 设计 | 未来可换其他 judge（Hook 接口预留） |
| mx + th 双国 | 共用 L1，L2 prompt 按国分别注入 schema |

### 1.2 ❌ 非目标
| 项 | 推迟到 | 理由 |
|---|---|---|
| **自动 ack（取代人工审核）** | 不做 | CLAUDE.md artifact 安全：SQL 仅是待审核 artifact |
| 真正执行 SQL | V2+ | V1 仅生成不执行 |
| 自动连接生产库 | 不做 | 同上 |
| 性能 EXPLAIN 分析 | V2 | 需要数据库 EXPLAIN 权限，V1 没有 |
| ML 风险评分模型 | V3 | 规则 + LLM 已满足 V1 目标 |
| **修改 `data_acquisition_agent/orchestrator.py` 内部** | 不做 | PLANNING.md Surgical Hard Boundary，163 tests 锁定 |

---

## 2. L1 规则引擎（毫秒级，对应 Harness §8 命令级）

### 2.1 正则黑名单

```python
# data_acquisition_agent/sql_judge/rules.py
import re

DDL_BLACKLIST = [
    r"\bDROP\s+(TABLE|DATABASE|SCHEMA|VIEW|INDEX)\b",
    r"\bTRUNCATE\s+(TABLE\s+)?\w+",
    r"\bALTER\s+(TABLE|DATABASE|SCHEMA)\b",
    r"\bCREATE\s+(TABLE|DATABASE|SCHEMA|VIEW)\b",
    r"\bGRANT\s+",
    r"\bREVOKE\s+",
]

DML_DANGEROUS = [
    r"\bDELETE\s+FROM\s+\w+\s*(?!.*\bWHERE\b)",   # DELETE 无 WHERE
    r"\bUPDATE\s+\w+\s+SET\b(?!.*\bWHERE\b)",     # UPDATE 无 WHERE
]

def check_blacklist(sql: str) -> tuple[bool, str | None]:
    """返回 (allow, reason)"""
    sql_normalized = re.sub(r'\s+', ' ', sql.strip())
    for pattern in DDL_BLACKLIST:
        if re.search(pattern, sql_normalized, re.IGNORECASE):
            return False, f"DDL 被禁止：匹配模式 {pattern}"
    for pattern in DML_DANGEROUS:
        if re.search(pattern, sql_normalized, re.IGNORECASE):
            return False, f"危险 DML：匹配模式 {pattern}"
    return True, None
```

### 2.2 AST 静态分析（sqlglot）

```python
# data_acquisition_agent/sql_judge/ast_analyzer.py
import sqlglot
from sqlglot import exp

def analyze_ast(sql: str) -> tuple[bool, list[str]]:
    """
    返回 (allow, warnings)
    - allow=False 时 warnings 是 block 原因
    - allow=True 但 warnings 非空 = 警告但放行
    """
    import logging
    from sqlglot.errors import SqlglotError

    try:
        parsed = sqlglot.parse_one(sql, dialect="starrocks")
    except SqlglotError as e:
        # sqlglot 全部子类（ParseError / TokenError / OptimizeError 等）正常解析失败 → block。
        return False, [f"SQL 语法错误：{type(e).__name__}: {e}"]
    except Exception as e:
        # 非 sqlglot 抛出的意外异常（如 RecursionError）：日志记录 + 保守 block，
        # 但绝不捕获 SystemExit / KeyboardInterrupt / GeneratorExit（这三个继承 BaseException 不被 Exception 捕获，
        # 自然冒泡，进程可正常中断）。
        logging.getLogger(__name__).error("ast_analyzer 非预期异常 %s: %s", type(e).__name__, e)
        return False, [f"SQL 解析意外异常：{type(e).__name__}"]

    warnings = []
    block_reasons = []

    # 检查 1: SELECT * 且无 LIMIT
    selects = list(parsed.find_all(exp.Select))
    for sel in selects:
        is_star = any(isinstance(e, exp.Star) for e in sel.expressions)
        has_limit = sel.args.get("limit") is not None
        has_where = sel.args.get("where") is not None
        if is_star and not has_limit and not has_where:
            block_reasons.append("SELECT * 同时缺少 WHERE 和 LIMIT，可能导致全表扫")
        elif is_star and not has_limit:
            warnings.append("SELECT * 缺少 LIMIT，建议加 LIMIT 1000")

    # 检查 2: JOIN 数量过多（> 5）
    joins = list(parsed.find_all(exp.Join))
    if len(joins) > 5:
        warnings.append(f"JOIN 数量 {len(joins)}，性能可能差")

    if block_reasons:
        return False, block_reasons
    return True, warnings
```

> ⚠️ **V1 不做子查询嵌套深度检查**（C5 修复）：早期草稿曾基于 sqlglot `node.args["expressions"]` 写过 `depth_of()` 递归示例，但实测该字段返回的是 SELECT **投影列**（`a, b`）而非子查询节点（子查询位于 `args["from"] / args["where"]` 等），导致 `depth_of()` 对任意嵌套深度都返回 0、警告永不触发。深度问题在 V1 由 L2 LLM 语义层捕获；如 V2 需引入 AST 层深度检查，正确方法是 `find_all(exp.Subquery)` 计算最深 ancestor 路径。本 Plan 08 ast_analyzer.py 与本 Spec § 2.2 已对齐为「不做深度检查」。

### 2.3 L1 综合判定

```python
def l1_check(sql: str) -> dict:
    """
    返回:
    {
        "verdict": "allow" | "block" | "warn",
        "reason": str | None,
        "warnings": list[str]
    }
    """
    # 黑名单优先
    blacklist_pass, bl_reason = check_blacklist(sql)
    if not blacklist_pass:
        return {"verdict": "block", "reason": bl_reason, "warnings": []}

    # AST 分析
    ast_pass, ast_msgs = analyze_ast(sql)
    if not ast_pass:
        return {"verdict": "block", "reason": "; ".join(ast_msgs), "warnings": []}

    if ast_msgs:
        return {"verdict": "warn", "reason": None, "warnings": ast_msgs}

    return {"verdict": "allow", "reason": None, "warnings": []}
```

### 2.4 性能预算

| 操作 | 预算 |
|---|---|
| 黑名单正则匹配 | < 5ms |
| sqlglot AST 解析 | < 30ms |
| 完整 L1 检查 | **< 50ms** |

---

## 3. L2 LLM 审查（对应 Harness §8 工具级 + 审批级）

### 3.1 调用条件

**L1 通过才调 L2**（成本控制）：
- L1 verdict = "block" → 不调 L2，直接进反思循环
- L1 verdict = "allow" / "warn" → 调 L2

### 3.2 模型选择

- **gemini-flash**（成本约 gemini-pro 的 1/10）
- 输入：schema + few-shot（来自 learned/）+ 当前 SQL + L1 warnings
- 输出：JSON `{pass: bool, suggestion: str | null, severity: "low" | "medium" | "high"}`

### 3.3 Prompt 模板

```python
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
1. **语义正确性**: SQL 是否正确表达了用户需求？
2. **字段正确性**: 引用的字段名是否在 schema 中存在？
3. **性能合理性**: 是否有明显性能问题（不必要的 JOIN、子查询过深）？
4. **数据安全**: 是否会泄露敏感字段（密码、token、手机号明文）？
5. **业务规则**: 是否符合业务约定（如时间窗口默认 7 天）？

## 输出格式（严格 JSON）
{{
  "pass": true | false,
  "severity": "low" | "medium" | "high",
  "suggestion": "如果 pass=false，给出具体修复建议；否则为 null",
  "reasoning": "判断理由，不超过 200 字"
}}
"""
```

### 3.4 输出解析（Pydantic v2 校验）

```python
# data_acquisition_agent/sql_judge/schemas.py
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal, Optional


class L2ReviewResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)   # Pydantic v2 推荐

    pass_: bool = Field(alias="pass")   # JSON key 仍是 "pass"
    severity: Literal["low", "medium", "high"]
    suggestion: Optional[str] = None
    reasoning: str
```

> **调用约定**（R7-N1 准确修订）：LLM 返回的 raw JSON dict 含 `"pass"` key（Python 保留关键字）。`L2ReviewResult(**data)` 在运行时**不会** SyntaxError——`**dict_unpack` 允许任意 string key（包括 Python 关键字）。但混用 `(**data)` vs `model_validate(data)` 容易造成 alias / 字段名 / kwargs 三套语义混乱。**统一用 `L2ReviewResult.model_validate(data)`**：单一 v2 入口点、跨 LLM/嵌套/测试三处调用一致、未来 alias 调整时无需 audit `**` 散落。

---

## 4. SQLGen ↔ Judge 反思循环（对应 Harness §10 错误三板斧）

### 4.1 流程图

```
┌─────────────────────────────────────────────────────────┐
│ Round 1: SQLGen 生成 SQL                                 │
└─────────────────────────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ L1 规则检查                                              │
│   ├── verdict=allow → 进 L2                              │
│   ├── verdict=warn  → 进 L2（带 warnings）              │
│   └── verdict=block → 反思（带 L1 reason）              │
└─────────────────────────────────────────────────────────┘
                       ↓
┌────────────────────────────────────────────────────────────┐
│ L2 LLM 审查                                              │
│   ├── pass=true  → 进入人工 ACK 预览 ✅（已减轻审核负担） │
│   └── pass=false → 反思（带 L2 suggestion）             │
└────────────────────────────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ 反思（喂回 SQLGen）                                      │
│   "上次生成的 SQL 有问题：{reason}                       │
│    建议修复方向：{suggestion}                            │
│    请重新生成 SQL。"                                     │
└─────────────────────────────────────────────────────────┘
                       ↓
                   Round 2 / 3
                       ↓
       ┌─────────────────────────────┐
       │ 3 轮内通过？               │
       │   是 → 进入人工 ACK 预览 ✅ │
       │   否 → 走 ack_bus 人审 ⚠  │
       └─────────────────────────────┘
```

### 4.2 代码结构（概念示意）

> ⚠️ **本节为概念示意。权威完整实现见 [Plan 08 Phase 3 Task 3.1](../plans/08-sql-judge-plan.md#task-31-实现-reflection-loop)**（C7 修复：避免在 Spec 与 Plan 同时维护两份代码导致漂移）。Plan loop.py 相比下方草图额外做了：
> - 函数签名采纳 `(nl_query, country, schema, sql_gen_fn, few_shot_examples="")` 顺序，避免 sql_gen_fn 横在 schema 前
> - 透传 `few_shot_examples` 给 `l2_review` 以兑现 § 3.3 few-shot 承诺
> - `last_sql` 重复 SQL 检测：连续两轮输出相同 SQL → 提前 break，兑现 § 8.1 风险表「history 检测重复 SQL 提前退出」承诺
> - history 序列化用 Pydantic v2 `model_dump(by_alias=True)` 而非 v1 已弃用 `.dict()`，并保留 `pass` JSON key（C6 修复）
> - `history[-1]["sql"] if history else ""` 兜底，避免空 history 时 IndexError

```python
# data_acquisition_agent/sql_judge/loop.py — 概念草图

MAX_ROUNDS = 3

def reflective_sql_gen(nl_query: str, country: str, schema: str,
                       sql_gen_fn, few_shot_examples: str = "") -> dict:
    """
    返回:
    {
        "final_sql": str,
        "rounds": int,
        "verdict": "passed" | "failed_to_human",
        "history": [{"round": int, "sql": str, "l1": dict, "l2": dict | None}, ...]
    }
    """
    history = []
    feedback = None
    last_sql = None

    for round_idx in range(1, MAX_ROUNDS + 1):
        sql = sql_gen_fn(nl_query, country, feedback)

        # 重复 SQL 提前退出（防 LLM 卡死）
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
        round_record["l2"] = l2_result.model_dump(by_alias=True)   # Pydantic v2
        history.append(round_record)

        if l2_result.pass_:
            return {"final_sql": sql, "rounds": round_idx,
                    "verdict": "passed", "history": history}

        feedback = f"L2 拒绝（severity={l2_result.severity}）：{l2_result.suggestion}"

    return {
        "final_sql": history[-1]["sql"] if history else "",
        "rounds": len(history),
        "verdict": "failed_to_human",
        "history": history
    }
```

### 4.3 集成到 DataAcq 的“Sidecar模式”（不改 orchestrator.py）

> **关键约束**：PLANNING.md Surgical Hard Boundary 明确“`data_acquisition_agent/` 任何 .py 锁定 163 tests”。本 Plan **不修改 `orchestrator.py` 内部**，采用“Sidecar Wrapper”模式。
>
> ⚠️ **开放问题 — sidecar 物理位置**（R7-H1 措辞收紧）：新增的 `sql_judge/` 子目录与类型上属于 `data_acquisition_agent/` 包，严格说是 Surgical Hard Boundary 的**边界澄清问题**（PLANNING.md 指 11 个现有核心 .py 锁定，query_data.py docstring 措辞 「不动 data_acquisition_agent 任何文件」可读为 「现有文件」也可读为 「整个包」）：
> - 候选 A（默认）：`data_acquisition_agent/sql_judge/`。物理就近便于审计，现有 11 个核心 .py **一字不动**，仅新增子目录（锁定范围 = “现有文件不修改”的读法下不受影响）。
> - 候选 B：`app/services/sql_judge/`。完全脱离 da-agent 包，包边界零歧义；代价 = 跨包 import + audit 路径变长。
> - **决策门 → 不是 「默认 A + 用户不推翻即生效」**：Spec/Plan 内联代码示例按 A 写，但作为 Surgical Hard Boundary 的边界澄清问题，**必须在 Plan Phase 0 Task 0.0 由用户显式确认**后才进入实施。如用户推翻为 B，Plan/Spec 内 11+ 处 `data_acquisition_agent/sql_judge/` 需同步替换为 `app/services/sql_judge/`，以及 wrapper 内 `Path(__file__).resolve().parents[1] / "configs"` 需调为 `parents[2] / "data_acquisition_agent" / "configs"`。

```python
# data_acquisition_agent/sql_judge/wrapper.py（新文件，不改 orchestrator.py）
"""
Sidecar wrapper：包装现有 DataAcquisitionOrchestrator.generate()，
在原 orchestrator 返回的 GenerateResponse 上多走一轮反思循环。
返回类型与原 orchestrator 一致 = GenerateResponse，调用方不需变。
"""
import os
from data_acquisition_agent.orchestrator import DataAcquisitionOrchestrator
from data_acquisition_agent.schemas import GenerateRequest, GenerateResponse
from data_acquisition_agent.sql_judge.loop import reflective_sql_gen


class JudgedDataAcquisitionOrchestrator:
    """在原 orchestrator 外面加一层 judge，不侵入 163 tests 锁定区。"""

    def __init__(self):
        self._inner = DataAcquisitionOrchestrator()

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        # 1. 先调原 orchestrator。baseline 是 Pydantic GenerateResponse 实例。
        baseline_response = self._inner.generate(request)

        # 2. 兑底开关：SQL_JUDGE_ENABLED=0 直接返回原费
        if os.getenv("SQL_JUDGE_ENABLED", "1") == "0":
            return baseline_response
        # 3. 原 orchestrator 未生成 sql（python-only / 报错）→ judge 无从介入，原费返回
        if not baseline_response.sql:
            return baseline_response
        # 4. R7-M2: V1 scope = query_only / EXTRACT only。build_table_script artifact 含
        # CREATE/DROP/ALTER 是 intended 行为，L1 黑名单会全部 block。这类 artifact
        # 直接走人审 ACK，不经 judge。
        if baseline_response.sql_kind == "build_table_script":
            return baseline_response

        # 5. 调反思循环。sql_gen_fn 遵从 loop 定义的 (nl_query, country, feedback) -> sql_str 签名
        # feedback 注入机制：拼接到 natural_language_request，原 orchestrator 看到的就是
        # “V1: prepend 反思反馈 + 原原本本用户 NL”，不改 orchestrator 签名。
        original_nl = request.natural_language_request
        country_str = request.target_country.value

        def sql_gen_fn(nl_query: str, country: str, feedback: str | None) -> str:
            if feedback is None:
                # 首轮 — 已有 baseline_response.sql，不重跑
                return baseline_response.sql
            judged_request = request.model_copy(update={
                "natural_language_request": (
                    f"上轮生成的 SQL 有问题，请根据以下反馈重新生成：\n{feedback}\n\n"
                    f"原始需求：\n{original_nl}"
                ),
            })
            new_resp = self._inner.generate(judged_request)
            return new_resp.sql or ""

        # V1 stopgap (M3/R4-M1 修复)：Plan 07 未上线前，schema 直接读 `data_acquisition_agent/configs/`
        # 下的 `<country>.local.yaml → <country>.yaml` YAML 文本作为裸全表 schema（§ 6.2）。
        # Plan 07 上线后可改为调 knowledge_base 路由后精简版，调整点仅限本函数体。
        schema_text = self._load_schema_for_judge(country_str)

        judge_result = reflective_sql_gen(
            nl_query=original_nl,
            country=country_str,
            schema=schema_text,
            sql_gen_fn=sql_gen_fn,
        )

        # 6. R7-H2 修复：failed_to_human 时 final_sql 是最后一轮被 L1/L2 reject 的 SQL，
        # 比 baseline 还危险，绝不能静默回写。保留 baseline_response 不变，让人工 ACK
        # 路径（agent_loop.py 仍要用户确认）处理原 baseline。只有 verdict=="passed" 才合并。
        if judge_result["verdict"] != "passed":
            return baseline_response

        merged = baseline_response.model_copy(update={
            "sql": judge_result["final_sql"],   # passed 路径必有 final_sql，无 None 兑底必要
        })
        # V1 不在 GenerateResponse 上携带 judge_history — 避免动 schema。
        # V2+ 可在 schemas.GenerateMetadata 上加 `extra: dict | None` 字段携带 history（本 Plan 不落地）。
        return merged

    @staticmethod
    def _load_schema_for_judge(country: str) -> str:
        """V1 临时实现：依次尝试 `<country>.local.yaml` → `<country>.yaml`。
        路径验证 (2026-05-06)：`data_acquisition_agent/configs/` 下存在
        `mexico.local.yaml` / `mexico.yaml` / `thailand.yaml` / `indonesia.yaml` /
        `pakistan.yaml` / `philippines.yaml`。**V1 仅 mx + th 在范围内**且能命中
        `<country>.yaml`；其余 3 国（indonesia / pakistan / philippines）暂不在 V1
        范围，但 fallback 链保留作为未来扩展接口（不动 wrapper 代码，未来扩展时
        把 Task 4.5 对应测试加回即可）。Plan 07 完成后可改为 knowledge_base 路由
        后精简版。"""
        from pathlib import Path
        cfg_dir = Path(__file__).resolve().parents[1] / "configs"
        candidates = [
            cfg_dir / f"{country}.local.yaml",   # mx 优先（包含本地调优）
            cfg_dir / f"{country}.yaml",          # V1 mx + th 命中；其余 3 国未来扩展接口
        ]
        for p in candidates:
            if p.exists():
                return p.read_text(encoding="utf-8")
        return "(schema unavailable)"
```

**关键点**：
- 新文件 `wrapper.py`/`loop.py`/`l1.py`/`llm_reviewer.py` 均在 `data_acquisition_agent/sql_judge/` 新子目录 — 不动现有 11 个核心 .py 中任一个
- 现有 163 tests 不需重跑（原 orchestrator `generate()` 返回值不变，Wrapper 在上面复合）
- 返回类型仍是 `GenerateResponse`，调用方 [tools/query_data.py](app/services/orchestrator_agent/tools/query_data.py) `gen_resp.sql or ""` 表达式零改动
- feedback 注入设计：拼接到 `natural_language_request`，不改原 orchestrator 签名（严格遵守 Surgical Hard Boundary）
- 重复 SQL 检测 + MAX_ROUNDS=3 由 `loop.py` 负责（深度防御 §8 末身 防卡死）
- 凭据扫描已由原 orchestrator `_enforce_output_policies` 在 baseline_response 返回前完成（只要注入凭据、原 orchestrator 会报 `CREDENTIAL_LEAK`），**Wrapper 层不重复扫**。

**调用方接入点**（在「not 锁定」区域）：
[`app/services/orchestrator_agent/tools/query_data.py`](app/services/orchestrator_agent/tools/query_data.py) 需同时修改 **import 行 + 实例化行**（合计 2 处）：
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
该文件 [tools/query_data.py](app/services/orchestrator_agent/tools/query_data.py) **不在** PLANNING.md Surgical 锁定区（锁定区是 `data_acquisition_agent/`）。L8 docstring 明确写「不动 data_acquisition_agent 任何文件」 — 本 Plan 未违反。

### 4.4 LLM 调用必经 ModelClient
```python
# ❌ 错误：直接 import google.genai、anthropic 等
# ❌ 错误：client.generate(prompt, route_key=...) — ModelClient 没有该方法
# ✅ 正确：
from app.core.model_client import ModelClient
client = ModelClient()
result = client.generate_structured(
    skill_name="sql_judge_l2",
    prompt=prompt,
    fallback_result={"pass": True, "severity": "high",
                     "suggestion": None, "reasoning": "mock fallback"},
    response_schema=L2_RESPONSE_SCHEMA,   # JSON Schema dict，可选
    route_key="sql_judge.l2",            # 与 config.yaml routes 点号风格一致
)
# result["structured_result"] 是实际 dict，result["status"] in ("ok", "model_unavailable")
l2 = L2ReviewResult.model_validate(result["structured_result"])   # Pydantic v2 推荐
```
`config.yaml::llm.routes` 必须新增 `sql_judge.l2: gemini`（与现有 9 条 route 的点号风格一致）。**不新增 gemini_flash 独立 provider**（现有 gemini provider 已是 gemini-2.5-flash，避免多一个名字造成混乱）。Maestro Spike 后可将这一行反转为 `claude_maestro`。

---

## 5. Hook 设计（V2+ 扩展点预告 — 本 Plan 不落地）

> ⚠️ **本章为设计预告**，V1 Plan 08 **不实现** `BaseSQLJudge` 抽象。V1 仅有具体的 `l1_check` 函数 + `l2_review` 函数，调用点仅限 `loop.py`。本章作为 V2+ 接入其他 judge（安全扫描 / EXPLAIN / 人审）的预设计点，避免未来不兼容。

### 5.1 抽象接口

```python
# data_acquisition_agent/sql_judge/base.py
from abc import ABC, abstractmethod

class BaseSQLJudge(ABC):
    @abstractmethod
    def review(self, sql: str, context: dict) -> dict:
        """返回标准化的 review 结果"""
        ...

class L1RuleJudge(BaseSQLJudge):
    def review(self, sql: str, context: dict) -> dict:
        return l1_check(sql)

class L2LLMJudge(BaseSQLJudge):
    def __init__(self, model: str = "gemini-flash"):
        self.model = model
    def review(self, sql: str, context: dict) -> dict:
        return l2_review(sql, context["schema"], context["nl_query"], context.get("l1_warnings", []))
```

### 5.2 未来扩展点

- `L3SecurityJudge`: 接公司安全扫描器
- `L4PerformanceJudge`: 接 EXPLAIN 分析（V2 实现）
- `L5HumanInLoopJudge`: 强制走人审（敏感场景）

---

## 6. 开放问题

### 6.1 L2 结果是否盲信？
- 选项 A：盲信（L2 pass=true 直接进入人工 ACK 预览）
- 选项 B：双重审查（L2 pass=true 但 severity=high → 仍走人审）

> **推荐**: B（双重审查），高严重度场景保留人审。
>
> **V1 落地状态**（R7-M1 修复）：V1 loop 仅看 `pass_`，未谋求 `severity == "high"` 拦截（该细节下放 V2，使 loop.py 函数签名不变）。同时为兑底 LLM unavailable / parse 失败场景，V1 已将 `l2_review` 的 fallback 从 `pass=True, severity=high`（fail-open）改为 `pass=False, severity=high`（fail-closed）：LLM 不可用时快速走反思循环 → 3 轮 → `failed_to_human` → wrapper 保留 baseline_response 不动 → 人工 ACK 预览。
>
> **V2 跟进**：loop.py 可加 `if l2.pass_ and l2.severity == "high": continue` 分支实现完整 B；Spec § 8.1 风险表能加一行，不影响其他代码。

### 6.2 schema 注入用全表 vs 路由后精简版？
- 选项 A：全表 schema（保证 L2 看到完整字段）
- 选项 B：路由后精简（依赖 Plan 07 的 INDEX 路由）

> **推荐**：长期方向是 B（精简，节省 token），但 V2+ 才接入。
>
> **V1 实际选项 = A（V1 stopgap，M3 修复）**：Plan 07 在本 Plan 执行时尚未完成，因此 Plan 08 Phase 4 `_load_schema_for_judge` 直接读取 `data_acquisition_agent/configs/<country>.local.yaml → <country>.yaml` 整段 YAML 文本作为 schema 注入 L2 prompt（裸全表）。Plan 07 上线后再切换为 B 路径，调整点仅限 `wrapper.py::_load_schema_for_judge` 函数体，wrapper 公开签名不变。

### 6.3 反思失败后的 SQL 是否归档到 learned/？
- 选项 A：归档到 learned/failed/（用于评测改进）
- 选项 B：不归档（避免污染知识库）

> **推荐**: A，但放 `learned/{country}/failed/` 子目录，明确标注，不参与 BM25 默认召回。

---

## 7. 验收清单

### 7.1 Phase 0（baseline）
- [ ] `data_acquisition_agent/orchestrator.py` 现有 ack 路径签名摸清
- [ ] `sqlglot` 加入 `requirements.txt`（版本 ≥ 18.0.0）
- [ ] StarRocks dialect 支持验证（`sqlglot.parse_one(sql, dialect="starrocks")` 能跑通）

### 7.2 Phase 1-3（L1 + L2 + 反思）
- [ ] `data_acquisition_agent/sql_judge/rules.py` 实现 + unit test 覆盖 100% DDL
- [ ] `data_acquisition_agent/sql_judge/ast_analyzer.py` 实现 + unit test
- [ ] `data_acquisition_agent/sql_judge/llm_reviewer.py` L2 实现 + Pydantic 校验 + mock LLM 单测
- [ ] `data_acquisition_agent/sql_judge/loop.py` 反思循环实现 + unit test

### 7.3 Phase 4（集成 + 验收）
- [ ] 接入 `orchestrator.py` 的 ack 路径
- [ ] L1 拦下 100% DDL/TRUNCATE（单测覆盖 50 个 DDL 样例）
- [ ] **L2 拦下 ≥ 80% SELECT * 全表扫**（依赖 Plan 09 评测集 + 真实 LLM 调用，本 Plan 08 不做，避免 tautology mock）
- [ ] 反思循环 3 轮内成功率 ≥ 80%（依赖 Plan 09 评测集）
- [ ] 兑底人审路径不变（mx 回归测试通过）
- [ ] env var `SQL_JUDGE_ENABLED=0` 能关闭整个 judge 层
- [ ] § 4.3 wrapper `_load_schema_for_judge` 路径 fallback 正确到 `<country>.yaml`（验收脚本：Plan Task 4.5 `test_schema_loader.py` 6 passed）

---

## 8. 风险与回退预案

### 8.1 已知风险

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 反思循环死循环（LLM 反复输出同样错误的 SQL） | 中 | 中 | MAX_ROUNDS=3 强制截断；history 检测重复 SQL 提前退出 |
| L2 LLM 自身 hallucination（说 pass 但其实有问题） | 中 | 高 | L1 已拦下结构性问题，L2 主要管语义；评测集兜底 |
| sqlglot 不支持某些 StarRocks 特殊语法 | 低 | 中 | parse 失败时 ast_analyzer 返回 `(False, ["SQL 语法错误"])`，走 L1 block 路径（保守）；**不**静默降级为纯正则（避免误放过未知语法的 DDL）。后续 Phase 4 出现误杀时，手动在 fixtures 补上该语法样本、重试 sqlglot 升级、或在 ast_analyzer 里为该类语法加补丁 |
| L2 调用 latency 累加（3 轮 × 1s = 3s） | 中 | 低 | 用 gemini-flash 控制单次 < 500ms |

### 8.2 回退预案

**触发条件**: Phase 4 验收发现 SQL 通过率 < 90%（比无 judge 还差）

**回退步骤**:
1. 设置 `SQL_JUDGE_ENABLED=0` 关闭 judge 层
2. 排查是 L1 误杀、L2 误判还是反思 loop 死循环
3. 修复后再开启

---

## 9. 参考文档

- Harness Engineering 学习笔记 §10 Resilience 层
- Harness Engineering 学习笔记 §8 Security 层
- Harness Engineering 学习笔记 §11 Eval 层（评测集对接 Plan 09）
- `Agent搭建实战学习笔记.md` Q9 错误三板斧
- `CLAUDE.md` SQL/凭据安全 + artifact 安全约束
