# 数据采集 Agent（data_acquisition_agent V1+V2）— 技术方案文档

> 项目：Agent User Profile（墨西哥市场多 Agent 用户画像后端）
> 模块：data_acquisition_agent（V1 artifact 生成 + V2 受控执行）
> 模块类型：A — 代码实现模块
> 语言/框架：Python 3.x + FastAPI + Pydantic + pymysql + pandas
> 核心文件数：10 个源文件 + 14 个测试文件（914 行源码 + 153 passed tests）
> 开发日期：2026-04-29 ~ 2026-04-30
> 定位：面试技术方案沉淀

---

## 1. 需求背景

### 1.0 问题是怎么发现的（面试叙事起点）

| 步骤 | 内容 |
|------|------|
| **观察到什么** | 画像 SkillRegistry 需要 per-uid 的 app/behavior/credit 数据文件才能运行，但数据只存在 StarRocks 数仓中。分析师每次取数要：手写 SQL → 跳到 StarRocks client 执行 → 手工切片成 per-uid 文件 → 落到 `data/` → 画像才能跑。整条体力链路耗时 30-60 分钟/次 |
| **为什么这是个问题** | 墨西哥市场有数万 UID，手工切片不现实；且手工操作容易写错 SQL（DDL 误执行、凭据泄漏到日志）、切片格式不一致导致画像 Skill 读取失败 |
| **做了什么初步验证** | 确认 LocalUserRepository 期望的文件格式（app=csv 7 字段、behavior/credit=json prepared schema）；确认 StarRocks FE 兼容 MySQL 协议（pymysql 可直连）；确认 CLAUDE.md 的 artifact 安全条款允许"受控执行 query_only" |
| **为什么决定这样解决** | 分两步：V1 用 LLM 从自然语言生成 SQL（降低写 SQL 门槛），V2 把审核后的 SQL 自动执行 + 切片 + 落地（消除手工体力活）。不一步到位是因为 LLM 输出不稳定（JSON 解析 0/3 成功率），V2 不依赖 V1，分析师手工接力 |

### 1.1 问题
画像 SkillRegistry 的数据供给是纯手工操作，耗时长、易出错、格式不统一。

### 1.2 目标
- V1：自然语言 → LLM 生成 SQL/Python artifact（待人工审核）
- V2：审核后 SQL → 连 DB 执行 → 按 bucket 切片 → 落 per-uid 文件到 `data/<bucket>/by_uid/`
- DDL 永不执行（build_table_script → 422）
- 凭据零泄漏（不进 Settings / repr / log / response / error message）
- 全程 TDD，V1 72 tests + V2 71 tests = 153 passed

### 1.3 约束
- `data_acquisition_agent/` 是顶层独立 package（CLAUDE.md 受控例外），不进入 SkillRegistry
- LLM 调用只通过 `ModelClient`（V1 用），V2 不调 LLM
- DB 凭据不入 `app/core/config.py` Settings
- SQL 结果只落本地文件，不支持 streaming/分批写
- 错误响应使用固定短文本，不回显 SQL / DB error / 路径

### 1.4 验收标准
- 153 passed + 1 skipped（real LLM smoke placeholder）
- DDL 请求 100% 拒绝（422），不触发 DB 连接
- 端到端 smoke test：MySQL 272 行 / 7 UID → 7 个 CSV 落地，行数完全匹配
- T1-T4 安全测试全绿（凭据零泄漏、固定 error message、DDL 不连库、DML 拦截）

---

## 2. 技术架构

### 2.0 在系统全局中的位置

```
分析师自然语言需求                                    画像 SkillRegistry
       │                                                    ▲
       ▼                                                    │
┌─────────────────────────────────────────────────────┐     │
│          data_acquisition_agent                     │     │
│                                                     │     │
│  V1 /generate ──→ LLM ──→ SQL artifact              │     │
│       │              (人工审核 + 手改)               │     │
│       ▼                                             │     │
│  V2 /execute ──→ 守门 ──→ COUNT ──→ 执行 ──→ 切片   │     │
│                                    │                │     │
│                              per-uid CSV/JSON       │     │
│                                    │                │     │
│                              data/<bucket>/by_uid/  ├─────┘
└─────────────────────────────────────────────────────┘
```

| 角色 | 是谁 / 是什么 | 数据格式 / 接口 |
|------|------------|----------------|
| 上游（V1 输入） | 分析师自然语言 + 目标国家 | JSON: `{natural_language_request, target_country}` |
| 上游（V2 输入） | 分析师审核后 SQL + bucket 信息 | JSON: `{approved_sql, sql_kind, output_bucket, ...}` |
| 下游（V2 输出） | LocalUserRepository → 画像 SkillRegistry | per-uid CSV（app）或 JSON（behavior/credit）文件 |

**核心价值一句话**：没有这个模块，画像 SkillRegistry 没有数据可读——分析师每次要花 30-60 分钟手工取数切片。

### 2.1 整体流程

```
V1 Pipeline:
  GenerateRequest ──→ load_manifest(mexico)
                          │
                     assemble_prompt（5 个知识库 md + L1 redact）
                          │
                     ModelClient.generate（LLM 调用）
                          │
                     output_scanner（L2 凭据/Python/DDL 扫描）
                          │
                     GenerateResponse（sql + audit_report）

V2 Pipeline:
  ExecuteRequest ──→ enforce_pre_execution_gates（DDL/凭据/DML/多语句拦截）
                          │
                     open_starrocks_connection（env→pymysql 短生命周期）
                          │
                     precheck_row_count（COUNT(*) 包裹，超 100K → 413）
                          │
                     execute_query（主查询 → pandas DataFrame）
                          │
                     validate_bucket_schema（app=csv+7字段校验）
                          │
                     build_per_uid_payloads（groupby uid → bytes）
                          │
                     write_per_uid_atomic（.tmp + os.replace）
                          │
                     ExecuteResponse（filenames + metadata）
```

### 2.2 核心组件

| 组件 | 文件 | 职责 | 关键 API |
|------|------|------|---------|
| Schema 层 | `schemas.py` | V1+V2 全部 Pydantic model + validators | `GenerateRequest`, `ExecuteRequest`, `ErrorType` (12 类) |
| 知识库加载 | `manifest.py` | 国家 YAML → `CountryManifest` dataclass | `load_manifest(country) → CountryManifest` |
| L1 脱敏 | `redactor.py` | 11 family 正则替换 DB 凭据 | `redact(text) → (text, hit_count)` |
| L2 扫描 | `output_scanner.py` | 凭据回扫 + Python 黑名单 + SQL DDL 策略 | `scan_credentials()`, `check_sql_policy()` |
| Prompt 拼装 | `prompt_assembler.py` | 5 知识库注入 + CJK token 估算 + 800K 阈值 | `assemble_prompt(request, manifest)` |
| V1 编排 | `orchestrator.py` | manifest → prompt → LLM → scan → response | `DataAcquisitionOrchestrator.generate()` |
| API 路由 | `api.py` | /generate + /execute + 统一错误映射 | `router` (4 endpoints) |
| DB 连接 | `connection.py` | env → pymysql 短生命周期 + 凭据零泄漏 | `open_starrocks_connection()` |
| V2 执行 | `executor.py` | 守门 + COUNT + 执行 + pipeline 编排 | `run_execute_pipeline(request, request_id)` |
| V2 输出 | `output_writer.py` | schema 校验 + per-uid 切片 + atomic 写盘 | `write_per_uid_atomic(items, bucket_dir, ...)` |

### 2.3 调用关系

```
api.py
  ├── /generate → _get_orchestrator().generate(request)
  │     └── orchestrator.py
  │           ├── manifest.load_manifest(country)
  │           ├── prompt_assembler.assemble_prompt(req, manifest)
  │           │     └── redactor.redact(text)  [L1]
  │           ├── ModelClient.generate(prompt)  [LLM]
  │           └── output_scanner.*  [L2]
  │
  └── /execute → _run_execute_pipeline(request, rid)
        └── executor.py
              ├── manifest.load_manifest(country)
              ├── enforce_pre_execution_gates()
              │     └── output_scanner.{scan_credentials, scan_python_dangerous, check_sql_policy}
              ├── connection.open_starrocks_connection()
              ├── precheck_row_count(conn, sql)
              ├── execute_query(conn, sql) → DataFrame
              └── output_writer.*
                    ├── validate_bucket_schema(df)
                    ├── build_per_uid_payloads(df) → [(uid, bytes)]
                    └── write_per_uid_atomic(items) → filenames
```

---

## 3. 核心技术细节

### 3.1 双层安全扫描（V1 L1 + L2，V2 复用）

**为什么这样做**：知识库 md 文件可能含真实 DB 凭据（host/port/password），LLM 输出可能回显这些凭据或生成危险代码。V2 也复用 L2 扫描对 approved_sql 做守门。

| 函数 | 签名 | 作用 |
|------|------|------|
| `redact` | `(text: str) -> tuple[str, int]` | L1：11 family 正则替换，注入 LLM 前脱敏 |
| `scan_credentials` | `(text: str) -> list[str]` | L2：检测 LLM 输出是否含凭据 pattern |
| `scan_python_dangerous` | `(code: str) -> list[str]` | L2：检测 eval/exec/os.system 等 8 类危险调用 |
| `check_sql_policy` | `(sql, sql_kind, prefix) -> None` | L2：DDL 关键字检测 + build_table_script 前缀校验 |

**11 family 正则示例**：
```python
# host='192.0.2.10' → <DB_HOST>
# password='xxx'    → <DB_PASSWORD>
# Authorization: Bearer xxx → <BEARER_TOKEN>
```

### 3.2 V2 三层守门（enforce_pre_execution_gates）

**为什么这样做**：V2 直连 DB，安全边界必须比 V1 更严格。应用层守门是 DB RBAC 之外的第二道防线。

执行顺序（任一失败立即拒绝，不连库）：
```
Step 1: sql_kind == "build_table_script" → ddl_not_supported_in_v2 (422)
Step 2: scan_credentials(sql)           → credential_leak (422)
Step 3: scan_python_dangerous(sql)      → dangerous_code (422)  [defensive]
Step 4: check_sql_policy(sql, "query_only", prefix) → ddl_policy_violation (422)
Step 5: strip_comments + split(";") > 1 → ddl_policy_violation (422)  [多语句拦截]
```

**关键设计**：守门在 `open_starrocks_connection` 之前，DDL 请求永远不触发 DB 连接——T1 安全测试断言 `called["connect"] == 0`。

### 3.3 V2 凭据零泄漏机制

**为什么这样做**：CLAUDE.md Zero Tolerance 条款要求凭据不得进入 Settings / repr / log / response / error。

| 层 | 机制 |
|---|---|
| 加载 | `os.environ` 在 `open_starrocks_connection()` 函数体内读取，不存 module-level 全局 |
| 连接对象 | `_RedactedConnection.__repr__()` 返回固定 `"<RedactedStarRocksConnection>"` |
| 异常 | `DbUnreachableError` 固定 message `"database connection failed"`，`from None` 切断 chain |
| 错误响应 | 12 类 ErrorType 全部使用预定义常量字符串，不 f-string / 不 format |
| 测试 | T3 用 caplog 断言假密码 `FAKE_PW_DO_NOT_LEAK_42` 不出现在任何 log record |

### 3.4 V2 atomic 写盘（write_per_uid_atomic）

**为什么这样做**：画像 Skill 随时可能在读 `by_uid/` 目录，直接写会让 Skill 读到半写文件。

```
Step 1: mkdir .tmp_<request_id>
Step 2: 逐个 uid 写 payload 到 .tmp/
Step 3: if overwrite=false → 检查 bucket_dir 有无冲突
Step 4: 逐文件 os.replace(.tmp/uid.csv → bucket_dir/uid.csv)
Step 5: rmtree .tmp
失败时: rmtree .tmp, raise OUTPUT_WRITE_FAILED
```

**已知 trade-off**：`os.replace` 单文件层面 atomic（POSIX/Windows），但逐文件 replace 中途崩溃会出现"部分新部分旧"。Design Doc §8.4 明确接受此 trade-off，V3 可做 rsync-style 双目录。

### 3.5 COUNT(*) 包裹预检

**为什么这样做**：防止分析师提交 `SELECT * FROM huge_table` 导致内存爆炸（100K+ 行）。

```python
count_sql = f"SELECT COUNT(*) FROM ({sql_stripped}) AS da_v2_count"
# 执行 count_sql → 如果 > DA_MAX_RESULT_ROWS (100000) → result_too_large (413)
```

**注意**：pymysql 不直接支持 query timeout 参数，运行时 query timeout 由部署侧 connect_timeout 兜底，留 V3 加 `SET SESSION` timeout。

---

## 4. 设计决策与选型理由

| 决策点 | 选择了什么 | 为什么不选另一个 | 理由 |
|--------|----------|----------------|------|
| DB Driver | pymysql | sqlalchemy | V2 只需连接 + 执行 SQL + 拿结果，不需要 ORM；pymysql 轻量且 StarRocks 兼容 MySQL 协议 |
| 凭据存储 | os.environ 运行时读 | Settings 字段 | Settings.model_dump() 会把密码序列化出去，违反 Zero Tolerance |
| V1→V2 衔接 | 分析师手工接力 | 进程内串联 | V1 LLM JSON 不稳定（0/3），V2 不能依赖不可靠输入 |
| 错误 message | 预定义常量 | f-string 动态拼 | 防止 SQL / DB error / 表名 / 列名泄漏到 API response |
| Mock 策略 | monkeypatch + MagicMock | pytest-mock | 不引入新依赖，与 V1 风格一致 |
| 写盘原子性 | 单文件 os.replace | 跨文件事务 | 复杂度与收益不匹配，V2 文档化接受 crash-consistency trade-off |
| token 估算 | CJK×1.5 + 其他÷4 | tiktoken | 不引入第三方依赖，800K 阈值是保守估算不需要精确 |
| app bucket 格式 | 强制 csv | 允许 json | 与 LocalUserRepository._resolve_app_uid_file 对齐，csv + utf-8-sig 编码 |

---

## 5. 迭代过程

| 版本 | 改了什么 | 为什么改 | 效果 |
|------|---------|---------|------|
| V1 Step 3 | 建 9 个 Stub（schemas/manifest/redactor/output_scanner/prompt_assembler/orchestrator/api + 2 test stubs） | Vibe Coding 方法论：先定接口再填实现 | 所有模块签名确定，TDD 可以开始 |
| V1 Step 5 | 9 Phase TDD 实现（72 tests） | 按 Plan 逐 Task 执行 | 72 passed + 1 skipped |
| V1 prompt hardening | 注入 analyst_private_prefix + 默认 query_only + 禁 Python DB client | 安全加固：LLM 输出扫描虽有 L2 兜底，但 prompt 层纵深防御更好 | security scan 0 leak；但 LLM JSON 稳定性降到 0/3（结构化输出被约束过紧） |
| V2 Design Doc | 5 个 Tension Points 显式解决（DDL 执行 ↔ CLAUDE.md、凭据 ↔ Zero Tolerance、V1 不稳 ↔ V2 输入、路径泄漏、schema 耦合） | V2 连 DB 后安全边界完全不同，必须先对齐再写代码 | 所有张力都有明确解法 |
| V2 Step 3 | 建 7 个 Stub（connection/executor/output_writer + 4 test stubs）+ schemas/api/config 扩展 | 同 V1，先 Stub 后实现 | V2 接口签名确定 |
| V2 Plan 审核 | 补 scan_python_dangerous（Plan 遗漏 Design Doc §7.1 Step 2）、修正测试计数（11→13）、补 import os | VS Code Chat 交叉审核发现 5 处问题 | Plan 精确度从"可能出错"到"可无脑执行" |
| V2 Step 5 | 6 Phase TDD 实现（71 tests），16 commits | Claude Code 全量执行，153 passed 0 failed | V2 全量完成 |
| 端到端 smoke | MySQL 272 行 / 7 UID → V2 /execute → 7 CSV 落地 | 单元测试全过不代表集成没问题 | 行数完全匹配，格式一致 |
| V1 JSON 稳定性修复 | 三处修复：①`_parse_json_text` 预转义裸换行符 ②`_RESPONSE_SCHEMA` 加 `required` 5 key ③新增 NL→sql_kind 一致性检查（无建表意图但返回 build_table_script → 硬拒） | 0/3 成功率无法接受，V1→V2 全自动链路被阻断 | 3/3 成功，278 passed |

---

## 6. 踩坑记录

### 坑 1: V1 real LLM JSON 稳定性 0/3 → 3/3 修复

| 维度 | 内容 |
|------|------|
| **现象** | prompt hardening 后 real LLM 3 次调用全部返回 422：①Unterminated string（SQL 裸换行破坏 JSON）②key_count=3（缺 python + audit_report）③ddl_policy_violation（LLM 生成 CREATE TABLE） |
| **根因** | 三个独立根因：①`_parse_json_text` 第一次 `json.loads` 前不做 escape，裸 `\n` 直接炸 ②Gemini response_json_schema 没有 `required` 字段，模型自由省略 key ③prompt 的 "default query_only" 约束力不够，LLM 仍生成 DDL |
| **解决** | 三处单点修复（commit 32d64e0）：①`_parse_json_text` 预调 `_escape_control_chars_in_strings` ②`_RESPONSE_SCHEMA` 加 `required: 5 keys` ③新增 `_enforce_nl_sql_kind_consistency`（NL 无建表意图 + sql_kind=build_table_script → 硬拒 SCHEMA_VALIDATION_FAILED）+ prompt 加 STRICT DEFAULT rule |
| **教训** | LLM 结构化输出的三个独立失败模式要分别诊断分别修——WIP 阶段只做了"补默认值"绕过了②但没修根因，①③完全没碰。诊断时必须看 server 日志逐条分析，不能只看最终 HTTP 状态码 |

### 坑 2: Plan 测试计数错误（11→13）

| 维度 | 内容 |
|------|------|
| **现象** | V2 Plan 审核时发现 Task 3.1 预期 11 case，但实际数 test 有 13 个（含 7 parametrize + 1 build_table + 1 multi-stmt + 1 cred + 1 dangerous_python + 1 clean + 1 comment-strip） |
| **根因** | Plan 写手漏数了 parametrize 7 个中的 2 个重叠项（CREATE TABLE 在 build_table_script 和 query_only 各出现一次但 sql_kind 不同），加上 scan_python_dangerous 整个被遗漏 |
| **解决** | VS Code Chat 全量审核后直接修正 Plan 文件（11→13，汇总表 69→71，总计 141→143） |
| **教训** | Plan 审核必须逐个数测试用例——AI 写的 Plan 倾向于"看起来对"但实际计数经常差 1-2 |

### 坑 3: scan_python_dangerous 被 Plan 遗漏

| 维度 | 内容 |
|------|------|
| **现象** | Design Doc §7.1 Step 2 明确写了 `scan_python_dangerous(approved_sql) → dangerous_code 422`（defensive guard），但 Plan 的 enforce_pre_execution_gates 实现代码完全没有这一行 |
| **根因** | AI 生成 Plan 时"觉得 V2 不接 Python 所以跳过了"，但 Design Doc 写的是"保留为 defensive" |
| **解决** | 审核时发现，直接在 Plan 里补了测试 `test_gate_rejects_dangerous_python` + 实现调用 |
| **教训** | Plan 必须与 Design Doc 逐条交叉核对，AI 会"自作主张"跳过它认为不重要的条目 |

### 坑 4: PowerShell f-string 引号冲突

| 维度 | 内容 |
|------|------|
| **现象** | 在终端跑 `python -c "..."` 时，f-string 的花括号 `{df["uid"]}` 导致 PowerShell 把 `\` 解释为转义，SyntaxError: '[' was never closed |
| **根因** | PowerShell 对双引号内的反斜杠和花括号有特殊处理，与 Python f-string 冲突 |
| **解决** | 改用 `str()` 拼接替代 f-string，或在 Python 里用单引号 key：`df['uid']` |
| **教训** | 跨语言 CLI 调用（PowerShell → Python one-liner）要避免 f-string，改用 `.format()` 或字符串拼接 |

### 坑 5: 基线测试数与预期不符（72+1 vs 82+16）

| 维度 | 内容 |
|------|------|
| **现象** | Plan 写的基线是"V1 72 passed + 1 skipped"，但实际跑出 82 passed + 16 skipped |
| **根因** | V2 Step 3 建的 4 个 test stub 文件各有若干 `pytest.skip` 标记的 test，加上 V1 的其他测试文件，总数比 72+1 多 |
| **解决** | 修正指令中的基线数字为实际值 82+16，停止条件改为"0 failed" |
| **教训** | 基线数必须实际跑一次确认，不能从记忆中引用——Stub 文件的 skip test 会影响总数 |

---

## 7. 项目目录结构

```
data_acquisition_agent/
├── __init__.py              ← 空
├── configs/
│   └── mexico.yaml          ← 墨西哥知识库路径 + analyst_private_prefix
├── demo0/                   ← 脱敏后的知识库 md 文件（5 个）
├── schemas.py               ← V1+V2 全部 Pydantic model（155 行）
├── manifest.py              ← 国家 YAML → CountryManifest（55 行）
├── redactor.py              ← L1 凭据脱敏 11 family（33 行）
├── output_scanner.py        ← L2 安全扫描（88 行）
├── prompt_assembler.py      ← prompt 拼装 + token 估算（64 行）
├── orchestrator.py          ← V1 generate 编排（103 行）
├── api.py                   ← FastAPI router /generate + /execute（76 行）
├── connection.py            ← V2 env→pymysql 连接（52 行）
├── executor.py              ← V2 守门 + COUNT + 执行 + pipeline（143 行）
├── output_writer.py         ← V2 schema 校验 + 切片 + atomic 写（145 行）
└── tests/                   ← 14 个测试文件（153 passed + 1 skipped）
    ├── test_schemas.py           10 tests（V1 5 + V2 5）
    ├── test_manifest.py           3 tests
    ├── test_redactor.py          15 tests（11 parametrize + 4）
    ├── test_output_scanner.py    25 tests
    ├── test_prompt_assembler.py   9 tests
    ├── test_orchestrator.py      10 tests
    ├── test_api.py                5 tests（V1）
    ├── test_api_v2.py             9 tests（V2）
    ├── test_connection.py         5 tests
    ├── test_executor.py          22 tests
    ├── test_output_writer.py     14 tests
    ├── test_e2e_mock_llm.py       1 test（V1 e2e）
    ├── test_e2e_mock_executor.py 16 tests（V2 T1-T4 + happy path）
    └── test_smoke_real_llm.py     1 test（skipped placeholder）
```

---

## 8. 运行方式

```bash
# 前置条件
pip install -r requirements.txt   # 含 pymysql>=1.1.0

# 启动服务（mock LLM 模式，不需要 Google API key）
MODEL_MODE=mock uvicorn app.main:app --reload

# 启动服务（real LLM + DB 连接）
MODEL_MODE=vertex \
DA_DB_HOST=127.0.0.1 DA_DB_PORT=3306 \
DA_DB_USER=root DA_DB_PASSWORD=xxx DA_DB_DATABASE=dm_model \
uvicorn app.main:app --reload

# V1: 生成 SQL
curl -X POST http://127.0.0.1:8000/api/data-acquisition/generate \
  -H "Content-Type: application/json" \
  -d '{"natural_language_request":"查询墨西哥 uid 的 app 安装数据","target_country":"mexico"}'

# V2: 执行审核后 SQL
curl -X POST http://127.0.0.1:8000/api/data-acquisition/execute \
  -H "Content-Type: application/json" \
  -d '{"approved_sql":"SELECT uid,app_name,... FROM dm_model.yyp_tmp_x","sql_kind":"query_only","target_country":"mexico","approved_by":"analyst","output_bucket":"app","output_format":"csv","uid_column":"uid"}'

# 跑测试
python -m pytest data_acquisition_agent/tests/ -v
```

---

## 9. 结果总览

### 9.1 量化效果（Before vs After）

| 指标 | 改进前 | 改进后 | 提升 |
|------|-------|-------|------|
| 单次取数耗时 | 30-60 分钟（手工 SQL + 切片） | 1 次 API 调用 ~50ms | ×600+ |
| 切片错误率 | 手工切片格式不一致 | schema 校验 + atomic rename | 0 错误 |
| 凭据泄漏风险 | 手工操作可能 copy-paste 密码 | 双层扫描 + 固定 error message + repr 覆写 | 零泄漏（T1-T4 验证） |
| 测试覆盖 | 无 | 153 passed + 1 skipped | 从 0 到完整覆盖 |
| DDL 误执行风险 | 分析师可能在 client 跑错 SQL | 三层守门 + build_table_script 永远 422 | 应用层 100% 拦截 |

### 9.2 对下游模块 / 后续工作的价值

| 下游模块 / 工作 | 消费本模块的什么 | 如果没有本模块会怎样 |
|--------------|--------------|---|
| LocalUserRepository | `data/app/by_uid/<uid>.csv` 文件 | 无数据文件，画像 Skill 全部返回空 |
| AppProfileSkill | per-uid CSV（7 字段 schema） | 无 app 安装明细，无法做借贷风险/金融成熟度判断 |
| BehaviorProfileSkill | `data/behavior/by_uid/<uid>.json`（prepared schema） | 无行为事件，无法做用户画像 |
| 画像 SkillRegistry 整体 | 三个 bucket 的 per-uid 文件 | 整个画像系统"空转"——有代码但没数据 |

**解锁的能力**：分析师一个 API 调用就能把数仓数据"灌入"画像系统，画像 SkillRegistry 从此有了自动化数据供给。

### 9.3 已知局限 & 改进方向

| 局限 | 影响 | 改进方向 |
|------|------|---------|
| V1 LLM JSON 稳定性 0/3 | V1→V2 全链路不通，分析师必须手写 SQL | 修复 prompt + JSON repair 逻辑（独立 follow-up） |
| 跨文件 crash-consistency | 进程崩溃时 bucket_dir 半新半旧 | V3 rsync-style 双目录切换 |
| 无 query timeout | 慢查询可能卡住 worker | V3 加 `SET SESSION query_timeout` |
| 单一 connection profile | 只支持一个 DB 连接 | V3 多 profile 支持 |
| 无真实 StarRocks RBAC 测试 | 依赖部署侧 smoke checklist | 部署后 CI 加 RBAC 验证 |

---

## 10. 面试怎么讲这个项目

### 10.1 口述结构（STAR 格式，2-3 分钟）

> **Situation（30秒）**：
> 我在微软实习做墨西哥市场用户画像后端。画像系统需要 per-uid 的 app 安装 / 行为 / 征信数据文件，但数据只在 StarRocks 数仓里。分析师每次取数要手写 SQL、手工执行、手工切片成 per-uid 文件，一次要 30-60 分钟，而且格式经常不一致导致画像 Skill 读取失败。
>
> **Task（20秒）**：
> 我负责做一个数据采集 Agent 模块，分两个版本：V1 用 LLM 从自然语言生成 SQL 降低写 SQL 门槛，V2 把审核后的 SQL 自动执行 + 按 bucket 切片 + 落 per-uid 文件，让画像系统直接读到数据。
>
> **Action（80秒）**：
> 核心设计有三个亮点：第一是**双层安全扫描**——知识库注入 LLM 前做 L1 正则脱敏（11 family），LLM 输出后做 L2 回扫（凭据 + Python 黑名单 + SQL DDL 策略），V2 执行前还有三层守门（DDL 拦截 + 凭据扫描 + 多语句检测），DDL 请求永远不触发 DB 连接。第二是**凭据零泄漏机制**——DB 密码只在函数体内局部变量存在，连接对象 repr 返回固定占位符，异常 chain 用 `from None` 切断，错误响应全部用预定义常量字符串，T3 安全测试用 caplog 断言假密码不出现在任何 log record。第三是**atomic 写盘**——先写 `.tmp_<request_id>` 临时目录，全部写完后逐文件 `os.replace` 到目标目录，失败时 rmtree 回滚，画像 Skill 不会读到半写文件。
> 开发过程中遇到一个典型坑：V1 LLM 输出 JSON 稳定性 0/3——加固安全 prompt 后反而导致结构化输出失败。解决思路是 V2 设计上不依赖 V1 输出，分析师手工接力，容忍上游不可靠。
>
> **Result（20秒）**：
> V1+V2 共 153 个测试全绿，覆盖 12 类错误码。端到端 smoke test 用真实墨西哥 272 行 / 7 UID 数据验证通过，行数完全匹配。取数效率从 30-60 分钟/次降到 1 次 API 调用 ~50ms。整个模块 914 行源码，严格按 Vibe Coding 八步流程开发（Design Doc → Plan → TDD → 白盒审计）。

---

### 10.2 三个技术亮点（供面试官深挖用）

> **亮点 1**：双层安全扫描 + 三层守门
> 为什么值得讲：不是简单的正则匹配——L1 在输入侧脱敏、L2 在输出侧回扫、V2 守门在执行前拦截，三道防线各司其职。DDL 守门在 DB 连接之前（T1 断言 connect_count==0），这意味着即使应用层被绕过，DB RBAC 只授 SELECT 是第四道防线。

> **亮点 2**：凭据零泄漏的系统化设计
> 为什么值得讲：不是"别把密码写代码里"这么简单——Settings 不持有密码（防 model_dump 泄漏）、连接 repr 覆写（防 debug 打印）、异常 chain 切断（防 traceback 带出原始 message）、错误响应预定义常量（防 f-string 拼入 SQL/DB error）、T3 测试用 caplog 做 log-level 断言（防 logger 偷偷记录密码）。五层环环相扣。

> **亮点 3**：Vibe Coding 方法论驱动的全流程工程实践
> 为什么值得讲：不只是"写了代码"——Design Doc 5 个 Tension Points 显式解决设计张力、Plan 用五点检查法审核（发现并修正了 3 处计数错误和 1 处 Design Doc 偏差）、TDD 先写失败测试再实现、VS Code Chat 交叉审核 Plan、Claude Code 全量执行 16 commits。体现的是系统化的 AI 辅助编程方法论，不是"让 AI 一口气写完"。

---

### 10.3 高频追问 Q&A

| 面试官怎么问 | 我的回答方向 | 加分点 |
|------------|-----------|--------|
| "为什么用 pymysql 不用 sqlalchemy？" | V2 只需要连接 + 执行原始 SQL + 拿 cursor 结果，不需要 ORM。pymysql 是纯 Python 实现（无 C 依赖），且 StarRocks FE 兼容 MySQL 协议 | 提到 "right tool for the job"——ORM 是过度设计 |
| "凭据为什么不放 Settings？" | Pydantic BaseModel 的 `model_dump()` 会把所有字段序列化出来，如果密码在 Settings 里，任何 debug / 日志 / 错误处理不小心调了 model_dump 就泄漏了。`os.environ` 在函数体内读取，作用域最小 | 主动说"我们的 CLAUDE.md 有 Zero Tolerance 条款" |
| "V1 LLM 不稳定怎么办？" | V2 设计上不依赖 V1——分析师手工接力。这是一个 architecture-level 的容错决策，不是 retry 能解决的。LLM 结构化输出的可靠性是整个行业的痛点，V2 通过解耦规避了这个风险 | 主动提"加固安全反而降低了 JSON 成功率"这个 trade-off |
| "atomic 写盘为什么不用数据库事务？" | 目标是写文件不是写 DB。文件系统没有跨文件事务，`os.replace` 是 POSIX/Windows 上最接近 atomic 的操作。跨文件一致性用 `.tmp` 目录 + rmtree 回滚做了"best effort"，Design Doc 里明确记录了 crash-consistency trade-off | 主动说"我知道这不是完美方案"并说出 V3 改进方向（rsync 双目录） |
| "怎么保证 DDL 不被执行？" | 四层防线：应用层守门（正则 + 多语句检测）→ 应用层 sql_kind 拦截（build_table_script → 422 不连库）→ DB RBAC（账号只授 SELECT）→ 错误响应固定文本（不透传 DB error）。T1 测试断言 connect_count==0，T2 测试 7 类 DDL/DML 全部 422 | 提到 "defense in depth"——应用正则只是补充，DB RBAC 才是最强边界 |
| "153 个测试是怎么组织的？" | 按模块分文件（14 个 test file），每个模块 TDD 驱动（先写失败测试再实现）。V2 有独立的 T1-T4 安全测试 Phase（Plan 里是 Phase 6），与功能测试分离。用 monkeypatch + MagicMock mock DB 连接，不引入 pytest-mock 等额外依赖 | 提到"Plan 写了每个 Phase 的预期通过数，执行时逐 Phase 验证" |
| "如果重新做你会怎么改进？" | V1 的 prompt 设计应该一开始就加 JSON formatting 约束（而不是先跑通再加安全约束导致 JSON 不稳定）；V2 的 query timeout 应该在 V2 就做（而不是留 V3）；Plan 审核应该写自动化脚本数测试用例数（而不是人工数） | 体现反思能力，不说"我会写得更好" |
