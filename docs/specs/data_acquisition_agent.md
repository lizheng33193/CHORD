# data_acquisition_agent V1 Design Doc

状态：Design Doc 已确认，尚未进入 Step 3 架构设计和 Step 4 实现 Plan。

---

## ⚠️ 矛盾检测结果（强制项 #5，置顶）

### M-1（阻塞级，已有解决方案）：CLAUDE.md "运行时代码只在 app/ 下创建" ↔ "顶层独立 data_acquisition_agent/"
**解决方案**：在本次 Design Doc 写入同时更新 CLAUDE.md 的"文件存放规则"，登记 `data_acquisition_agent/` 及 `data_acquisition_agent/tests/` 为受控例外，并允许该子项目 import `app.core.*`。在该例外登记完成前，不得创建任何 `data_acquisition_agent/` 运行时代码或测试文件。

### M-2（语义级）："Business Stage 0" 概念在 SkillRegistry 中**不存在**
本 Doc 中"Business Stage 0"指**业务阶段语义**，data_acquisition_agent **不进 SkillRegistry**，是画像系统的上游。第 4 节显式区分。

### M-3（输入资料级）：埋点表名两份资料**不一致**
few.md 同时出现 `hive.dwb.dwb_b1_data_burying_point` 和 `hive.dwb_paimon.dwb_b1_data_burying_point`；流失归因 SOP 附录写 `dwb.dwb_b1_data_burying_point`。**V1 处理**：不在系统侧裁决，把不一致原样作为知识传给 LLM（few.md 全量注入），由 LLM 从上下文推断。Q-7 已确认 V1 不强约束（且 Q-7 决策不变：不加 manifest `preferred_table_name`）。

### M-4（语义对齐风险）：用户画像方案文档里的 "Skill 1–4" ≠ 现有 `app/runtime_skills/`
**V1 完全不依赖**画像方案文档里的 Skill 1–4——data_acquisition_agent V1 仅做"自然语言取数需求 → SQL/Python artifact"，**不做画像、不做分层、不做归因**。

### M-5（业务定义级）：mob1 各国窗口期不一致
墨西哥 = 结清后 7 天；巴铁 = 37 天固定窗口；印尼 = 同墨西哥 7 天。**V1 处理**：每国 manifest 只注入对应国家的知识库，避免跨国窗口定义混入。

---

## 1. Background / Problem

`MAPS-LZ` 项目当前的画像 Skill 链路（app/behavior/credit/comprehensive）依赖**已经准备好的 UID 列表 + 本地数据文件**。这些数据来源于：
- 数据分析师手工写 SQL（依赖经验 + few-shot 跑通的代码片段）
- 跑数仓（Hive / StarRocks via 内网代理）
- 切片成 UID 文件 + 各类 JSON / CSV
- 落到 `data/` 喂给画像 Skill

**痛点**：
1. SQL 撰写依赖个人经验，跨国家时反复出错（墨西哥 vs 印尼字段名不一致、印尼提现要用 `withdraw_risk_uuid`、墨西哥渠道是 `MEX017` / `MEXI` / `MEXICASH`）
2. 业务"黑话"（mob1、eKYC 拦截、首贷流失）映射到 SQL 条件需要查多份零散文档
3. 新人接手陡峭、复用率低、易出"鬼字段"和缺过滤条件错误

`data_acquisition_agent` 把 demo0/system_prompt.md 描述的"资深数据架构师"角色落地为**可调用的 LLM Agent**：自然语言需求 → 三阶段（**需求拆解 / 可审计推理摘要 → SQL/Python artifact → 自检审计报告**）→ 待审核的 artifact。

## 2. Business Goal

**面向用户**：内部数据分析师 / 风控策略 / 增长 / 画像团队

**V1 验收要点**：
- G1 给定一句"建表墨西哥 mob1 客群，取前 100 个 uid"自然语言，能产出**字段真实**（每个字段都能在 scheme.md 中找到）的 SQL
- G2 输出严格遵守 system_prompt.md 的三阶段结构，自检报告包含 A/B/C 三维核查项
- G3 风格"照搬 few.md"——few.md 没用时区转换就不加，墨西哥 channel filter 必须命中 `MEX017` 之一
- G4 整个 V1 不连任何数据库、不执行任何 SQL/Python，只生成 artifact 字符串
- G5 凭据全程脱敏（详见第 7 节）

**非目标**：不做画像 / 不做客群分层 / 不做流失归因 / 不做数据落地 / 不连库。

## 3. V1 Scope / Out of Scope

### In Scope
| 项 | 内容 |
|---|---|
| 国家覆盖 | 代码层多国架构（manifest 驱动），**仅墨西哥验证** |
| 客群覆盖 | **仅 mob1 流失**（Q-2 确认） |
| 交付形态 | FastAPI 路由，复用 `app/main.py` 实例（Q-3 确认） |
| 输入 | JSON：自然语言需求 + 目标国家 + （可选）目标动作类型 |
| 输出 | 结构化 JSON：`{reasoning_summary, sql, sql_kind, python, audit_report}` |
| SQL 类型 | `query_only`（默认推荐）/ `build_table_script`（仅用户明确要求建表时） |
| 知识库注入 | 全量塞 prompt（system_prompt + 4 份知识库，仅目标国一份）+ 3 条护栏（token 统计、脱敏、只注入目标国） |
| LLM 通道 | **复用 `app/core/model_client.py` 的 ModelClient**（Q-1 确认） |
| 凭据安全 | 加载层脱敏 + 输出层正则扫描 reject |
| 危险代码扫描 | LLM 输出 `python` 字段过黑名单 |
| 测试 | mock LLM 端到端 + 真实 LLM 跑墨西哥 mob1 一条 smoke 用例 |

### Out of Scope（V1 不做，留 V2+）
- ❌ 实际连数据库执行 SQL/Python
- ❌ 数据落地到 `data/` 与画像 Skill 自动衔接
- ❌ RAG / 向量检索（V1 全量塞 prompt）
- ❌ 知识库自动更新（V1 静态 manifest）
- ❌ 多轮对话 / clarification（V1 单 turn 请求-响应）
- ❌ 印尼 / 巴铁 / 泰国 / 菲律宾的实际验证（架构留位）
- ❌ 流式输出
- ❌ 三客群 no_apply / no_withdraw / withdraw、反欺诈特征（Q-2 确认仅 mob1）

## 4. System Position

### 业务阶段视角（Business Stage）
```
Business Stage 0：数据获取（人工触发或分析师调用）
  └── data_acquisition_agent  ← V1 在此处
       └── 输出：待审核的 SQL/Python artifact
       └── 分析师手工执行 → 数据落到 data/

Business Stage 1：画像
  └── SkillRegistry stage 0：app_profile / behavior_profile / credit_profile（并行）
  └── SkillRegistry stage 1：comprehensive_profile（依赖上面三者）
  └── SkillRegistry stage 2：product_advice / ops_advice（已建 Stub）
```

### 代码层定位（精确措辞）

`data_acquisition_agent/` 是**顶层独立 Python package**，与 `app/runtime_skills` 解耦，**不进入 SkillRegistry**；**V1 不启动独立服务，而是通过 `app/main.py include_router` 挂载到现有 FastAPI 进程中，复用现有 ModelClient、logger 和配置能力。**

```
MAPS-LZ/
├── app/                              # 现有画像系统
│   ├── runtime_skills/               # 不动
│   ├── core/model_client.py          # data_acquisition_agent V1 复用
│   ├── core/logger.py                # data_acquisition_agent V1 复用
│   ├── core/config.py                # data_acquisition_agent V1 复用配置
│   ├── main.py                       # data_acquisition_agent 通过 include_router 挂入此 FastAPI 实例
│   └── ...
├── data_acquisition_agent/           # ← V1 新增（顶层独立 Python package，CLAUDE.md 例外条款登记）
│   ├── __init__.py
│   ├── demo0/                        # 现有未追踪输入资料
│   ├── configs/
│   ├── api.py / orchestrator.py / ...   # 第 8 节展开
│   └── tests/
└── docs/specs/data_acquisition_agent.md   # 本 Doc 落地点
```

### 与 CLAUDE.md 关键约束的对齐
- "LLM 调用只通过 ModelClient" → ✅ V1 直接 import `app.core.model_client.ModelClient`
- "运行时代码只在 app/ 下" → ⚠️ V1 必须破例，CLAUDE.md 配套修改（M-1，覆盖 `data_acquisition_agent/` 及 `data_acquisition_agent/tests/`）
- "新 Skill 必须继承 BaseSkill 并在 SkillRegistry 注册" → ✅ data_acquisition_agent 不是 Skill，不适用
- "数据文件不进 git" → `demo0/` 是知识库不是数据；先在原目录完成凭据脱敏再入 git（详见第 7.5 节）

## 5. Input/Output Contract

### Request (POST 请求体)
```json
{
  "natural_language_request": "建表墨西哥 mob1 客群，取前 100 个 uid 的用户埋点数据",
  "target_country": "mexico",
  "target_action": "build_table_and_extract"
}
```
- `natural_language_request`：必填
- `target_country`：必填，枚举 `mexico / indonesia / pakistan / thailand / philippines`（V1 只测 mexico）
- `target_action`：可选枚举 `build_table / extract / build_table_and_extract`；缺省由 LLM 从自然语言中识别

### Response (200 OK)
```json
{
  "request_id": "uuid",
  "target_country": "mexico",
  "reasoning_summary": "string — LLM 输出的需求拆解与可审计推理摘要（Markdown），含目标锚定、业务语义解析、本地化映射和关键假设；不得要求或返回完整内部思维链。V1 不做嵌套 schema，整段透传，V2 再考虑结构化。",
  "sql": "WITH base_users AS (...) SELECT ... -- 待人工审核，不由系统执行",
  "sql_kind": "query_only",
  "python": "import pymysql\nconn = pymysql.connect(host=os.getenv('DA_DB_HOST'), ...)  # 待人工审核",
  "audit_report": {
    "schema_parity_check": [{ "table": "...", "fields": ["..."], "passed": true }],
    "localization_quirks_check": [{ "rule": "墨西哥渠道过滤 MEX017", "line_number": 12, "passed": true }],
    "business_rule_completeness_check": [{ "term": "mob1", "covered_aspects": ["..."], "passed": true }],
    "high_risk_ddl": false,
    "final_verdict": "代码已达标 / 需人工修改的注意事项"
  },
  "metadata": {
    "model": "gemini-3.1-pro-preview",
    "tokens_used": { "prompt": 12345, "completion": 678 },
    "token_estimate": 12000,
    "knowledge_files_loaded": ["mexico/system_prompt.md", "mexico/多国业务逻辑.md", "..."],
    "redaction_events": 0,
    "danger_scan_events": 0,
    "generated_at": "2026-04-29T..."
  }
}
```

### 字段约束
- `reasoning_summary`：`string`（必填非空），描述见上；**禁止要求或返回完整内部思维链**
- `sql`：`Optional[str]`
- `sql_kind`：`Optional[Literal["query_only", "build_table_script"]]`，`sql` 非空时必填
- `python`：`Optional[str]`
- **约束**：`sql` 与 `python` **至少一个非空**；两个均空 → 422 `schema_validation_failed`
- `audit_report`：必填非空对象，**Pydantic model `Config: extra = "allow"`**，容忍 LLM 多输出字段；当 `sql_kind == "build_table_script"` 时 `audit_report.high_risk_ddl` 必须为 `true`
- `metadata.tokens_used`：**best-effort**——若 ModelClient 不返回 token usage，则为 `null` 或缺省；`token_estimate` 始终由本端粗估并填充

### 错误响应
| 状态码 | error_type | 触发条件 |
|---|---|---|
| 400 | `bad_request` | `natural_language_request` 缺失 / `target_country` 不在枚举内 / 自然语言过长 |
| 400 | `prompt_too_large` | token 估算超过 model context window 阈值 |
| 422 | `schema_validation_failed` | LLM 输出 JSON 解析失败、缺字段、`sql`/`python` 都为空（已内置一次 retry） |
| 422 | `credential_leak` | LLM 输出层扫描命中明文凭据 → reject artifact |
| 422 | `dangerous_code` | LLM 输出层扫描命中危险代码 pattern → reject artifact |
| 422 | `ddl_policy_violation` | `sql_kind == "build_table_script"` 但 SQL 未限定分析师私有 schema/prefix；或 `sql_kind == "query_only"` 却含 DDL 语句 |
| 502 | `upstream_llm_error` | LLM 上游错误（透传 ModelClient 错误码） |

错误响应体示例：
```json
{ "error_type": "credential_leak", "message": "...", "request_id": "..." }
```

## 6. Knowledge Assets & Prompt Assembly

### 6.1 manifest 驱动的多国知识库（YAML，Q-4 确认）

每国一份 manifest，举例：
```yaml
# data_acquisition_agent/configs/mexico.yaml
country: mexico
display_name: 墨西哥
business_logic_md: data_acquisition_agent/demo0/各国数据知识库汇总/墨西哥/多国业务逻辑.md
all_examples_md: data_acquisition_agent/demo0/各国数据知识库汇总/墨西哥/all_examples .md  # 注意空格
schema_md: data_acquisition_agent/demo0/各国数据知识库汇总/墨西哥/scheme.md
few_md: data_acquisition_agent/demo0/各国数据知识库汇总/墨西哥/few.md
system_prompt_md: data_acquisition_agent/demo0/system_prompt.md
sql_dialect: starrocks  # Q-8 确认
analyst_private_prefix: dm_model.yyp_tmp_   # build_table_script 必须命中此前缀（举例）
```

**优势**：硬隔离 5 国文件名 quirks（few/few-shot、scheme/schema、含空格）；未来加国家只加 manifest，不动代码；`gem prompt.md` 不纳入 manifest（Q-6 确认），仅以 README 形式在 demo0 中说明为历史快照。

### 6.2 Prompt 拼装（概念描述）

每次请求按目标国家 manifest 装载 5 份 md（system_prompt + 4 份知识库），经过**凭据脱敏管线**后注入 LLM。Prompt 包含三块语义区：**system 区**承载角色与三阶段铁律；**knowledge 区**按目标国注入脱敏后的 4 份知识库；**user request 区**承载本次请求的国家、动作、自然语言原文，并在 prompt 末尾声明输出 JSON schema 契约（含 `sql_kind` 二选一与 `audit_report.high_risk_ddl` 联动规则）。

护栏：
1. **token 估算**：拼装前估算总 token，超过 model context window 阈值（建议 80%）→ 直接 400 `prompt_too_large`，不发 LLM
2. **脱敏先行**：所有 md 注入前必须经过 7.1 节的脱敏管线，未脱敏不得进 prompt
3. **国家隔离**：仅注入 `target_country` manifest 选中的 4 份知识库，禁止跨国混入

LLM 返回后做 **JSON parse + Pydantic schema 校验**（一次 retry on parse 失败），通过后进入 7.1 / 7.2 / 7.3 的输出层安全扫描，最后拼装 Response。**具体 Step 拆分留给 Step 4 Plan。**

### 6.3 Prompt cache 策略

system_prompt + 4 份知识库占大头（墨西哥 ~170 KB），每个国家这部分**完全静态**——理想的 prompt cache 命中区。但**功能正确性不依赖 cache**：cache miss 时仍能正确完成请求，只是慢且贵。

## 7. Safety

### 7.1 凭据脱敏管线（强制双层防御）

**凭据来源（部分脱敏列举，避免在 Doc 中复现明文）**：few.md 含 starrocks 风格凭据：
- `host='172.20.***'`、`host='10.20.***'`
- `user='e_***'`
- `port=<DB_PORT_REDACTED>`
- `password='4FM***'`
- `database='dm_***'`

**双层防御**：
| 层 | 触发时机 | 行为 |
|---|---|---|
| L1 加载层脱敏 | 读取每份 md 之后、注入 prompt 之前 | 正则替换：IP → `<DB_HOST>`、port=数字 → `<DB_PORT>`、user='e_*' → `<DB_USER>`、password='...' → `<DB_PASSWORD>`、database='dm_*' → `<DB_NAME>` |
| L2 输出层扫描 | LLM 返回 raw response 之后、Response 拼装之前 | 同样正则扫 LLM 输出的 `python` 字段 + 整个 `audit_report`；命中即 422 `credential_leak`，不返回 artifact |

**测试要求**：每条已知凭据对应一条单测验证脱敏命中。**测试 fixture 仅使用占位符风格的合成假凭据（如 `host='<FAKE_DB_HOST>'`、`password='FAKE_PASSWORD_REDACTED'`），不得在测试代码中嵌入真实明文凭据，也不得使用看似真实的假 IP。**

### 7.2 SQL 安全（artifact 二分策略）

artifact 性质：仅字符串，不执行。SQL 分两类，由 LLM 在响应中通过 `sql_kind` 字段声明：

| sql_kind | 允许语句 | 约束 | audit 联动 |
|---|---|---|---|
| `query_only`（默认推荐） | `SELECT` / `WITH` CTE / `LIMIT` | **禁止**任何 DDL（`CREATE` / `DROP` / `ALTER` / `TRUNCATE` / `INSERT` / `UPDATE` / `DELETE`） | `audit_report.high_risk_ddl = false` |
| `build_table_script` | `CREATE TABLE ... AS SELECT`、`DROP TABLE IF EXISTS` | **必须**限定在 manifest 声明的分析师私有 schema/prefix（如 `dm_model.yyp_tmp_*`）；不允许在生产 schema 上 DDL | `audit_report.high_risk_ddl = true`（强制） |

**输出层硬约束**：
- 若 `sql_kind == "query_only"` 但 SQL 中检出 DDL 关键字 → 422 `ddl_policy_violation`
- 若 `sql_kind == "build_table_script"` 但 DDL 目标未命中 manifest 私有 prefix → 422 `ddl_policy_violation`
- 若 `sql_kind == "build_table_script"` 但 `audit_report.high_risk_ddl != true` → 422 `schema_validation_failed`

**说明**：`query_only` 与 `build_table_script` 的并存不冲突——前者是默认安全档位，后者是用户**明确要求建表**时启用的高风险档位，二者互斥；V1 仍**不执行**任何 SQL，两类都是人工审核 artifact，运行时安全由分析师审完后自行负责。

### 7.3 Python 安全（输出层黑名单）
LLM 输出的 `python` 字段需通过：
- 黑名单 reject：`os.system`、`subprocess.run\(.*shell=True`、`\beval\(`、`\bexec\(`、`__import__\('os'\)`、`urllib.request.urlretrieve`、`shutil.rmtree`、`os.remove`、绝对路径写文件
- 凭据黑名单：硬编码 IP/password/user 字面量（即使经过 L1 脱敏，LLM 仍可能瞎编）
- 命中即 422 `dangerous_code`，记录 `danger_scan_events`

### 7.4 人工审核
Response 顶部要求前端展示警告 banner：「**生成的 SQL 和 Python 是 artifact，未由系统执行。请人工审核字段、过滤条件、凭据占位符之后再投入生产。**」`sql_kind == "build_table_script"` 时 banner 必须额外提示"含 DDL，目标 schema/prefix 必须二次核对"。V1 由调用方自行展示，后端不强制。

### 7.5 demo0 入 git 策略

**原始 `demo0/` 不得直接 `git add`。** 必须先在 `demo0/` **原文件**上完成凭据脱敏（替换明文为占位符 `<DB_HOST>` / `<DB_PORT>` / `<DB_USER>` / `<DB_PASSWORD>` / `<DB_NAME>`），通过凭据扫描后再 `git add`。**不建双目录**（不搞 `demo0_redacted/` 之类）。**脱敏为单独 mini-task**，不在 V1 主 Plan 内，但必须早于 demo0 首次 commit。脱敏 mini-task 的验收：扫描脚本对 `demo0/` 全目录跑一遍，零命中才算通过。

## 8. API Surface（概念级，不定最终路径）

> 以下目录仅为候选目标结构，用于 Step 3 架构设计输入；最终文件路径、模块拆分、测试文件名和 TDD 顺序以 Step 4 Plan 为准。

### 路由定位（Q-3 确认）
**复用 `app/main.py` 的 FastAPI 实例**，通过 `include_router` 挂入；进程共享 ModelClient、logger、配置。

### 端点（概念级，最终路径在 Plan 中定）
- `POST /api/data-acquisition/generate` — 主端点，请求/响应见第 5 节
- `GET  /api/data-acquisition/manifests` — 列出已注册国家（debug）
- `GET  /api/data-acquisition/healthz` — 探活：manifest 加载、ModelClient 探针

V1 Plan 可选择只实现 generate 端点，manifests / healthz 作为可选调试端点在 Plan 阶段评估。

### 目录骨架（候选）
```
data_acquisition_agent/
├── __init__.py
├── demo0/                       # 知识库（已存在，未追踪；7.5 节脱敏后入 git）
├── configs/                     # YAML manifest
│   ├── __init__.py              # 让工具识别为 package（即使 YAML 不需要）
│   ├── mexico.yaml
│   ├── indonesia.yaml           # 留位
│   ├── pakistan.yaml            # 留位
│   ├── thailand.yaml            # 留位
│   └── philippines.yaml         # 留位
├── api.py                       # FastAPI 路由（include 进 app/main.py）
├── orchestrator.py              # 拼装流程编排，直接 import app.core.model_client.ModelClient
├── manifest.py                  # manifest 加载 + 校验
├── prompt_assembler.py          # prompt 拼装
├── redactor.py                  # L1 脱敏
├── output_scanner.py            # L2 扫描 + Python 黑名单 + DDL 策略
├── schemas.py                   # Pydantic 请求/响应（含 error_type 枚举、sql_kind、extra="allow"）
└── tests/
    ├── __init__.py
    ├── test_redactor.py
    ├── test_manifest.py
    ├── test_prompt_assembler.py
    ├── test_output_scanner.py
    ├── test_schemas.py
    ├── test_e2e_mock_llm.py
    └── test_smoke_real_llm_mexico.py    # 慢，pytest marker
```

## 9. Logging / Testing Strategy

### Logging
- 复用 `app/core/logger.py`
- **凭据安全规则**：日志只记录 **文件路径、大小、SHA-256 hash、redaction hit count、token estimate**；**不打印知识库正文片段，即使脱敏后也不打印**
- 关键日志事件：
  - `manifest_loaded` (country, files=[{path, size, sha256}], total_bytes)
  - `redaction_applied` (file_path, hits_count)
  - `prompt_assembled` (token_estimate)
  - `llm_request_sent` / `llm_response_received` (latency, tokens_used_or_null)
  - `redaction_event` / `danger_scan_event` / `ddl_policy_violation_event` (path, pattern_matched)
  - `request_completed` / `request_failed` (status_code, error_type)

### Testing
| 测试 | 目的 | 形式 |
|---|---|---|
| Unit: redactor | 5 类已知凭据 → 必须命中（fixture 用合成假凭据，不嵌入真实明文） | pytest |
| Unit: manifest | 5 国 manifest 都能加载，文件路径都存在；`analyst_private_prefix` 字段格式校验 | pytest |
| Unit: prompt_assembler | 拼装顺序正确、目标国知识库注入、token 估算 | pytest |
| Unit: output_scanner | 已知危险 pattern + 漏网凭据 + DDL 策略（query_only/build_table_script 双向校验） → reject | pytest |
| Unit: schemas | 请求/响应 Pydantic 边界 case；`sql`/`python` 至少一非空；`sql_kind` 与 `audit_report.high_risk_ddl` 联动；`error_type` 枚举完整；`audit_report` `extra="allow"` 通过 | pytest |
| Integration: e2e mock LLM | ModelClient mock 模式跑完整端到端 | pytest |
| Smoke: real LLM mexico | mob1 一条用例，断言 SQL 含 `MEX017`、含 `HAVING COUNT(1)`、不含明文凭据、`sql_kind` 与 `high_risk_ddl` 一致 | pytest，标 `@pytest.mark.smoke`，CI 默认跳过 |

## 10. Open Questions / Decisions Required Before Plan

| ID | 问题 | 决策 / 处置 | 阻塞 Plan |
|---|---|---|---|
| ~~Q-1~~ | LLM 通道 | **已确认**：复用 `app/core/model_client.py` 的 ModelClient | — |
| Q-2 | V1 客群范围 | **已确认**：仅 mob1 流失 | — |
| ~~Q-3~~ | API 入口 | **已确认**：复用 `app/main.py`，include router | — |
| Q-4 | manifest 格式 | **已确认**：YAML | — |
| Q-5 | demo0 git 追踪 | **已确认**：原目录脱敏后入 git，不建双目录，脱敏为单独 mini-task（见 7.5） | — |
| Q-6 | gem prompt.md 处置 | **已确认**：不纳入 manifest，demo0 README 说明为历史快照 | — |
| Q-7 | 埋点表名不一致 | **已确认**：V1 不强约束；不加 manifest `preferred_table_name`，由 LLM + audit_report 处理 | — |
| Q-8 | SQL 方言 | **已确认**：`sql_dialect: starrocks` | — |

**主要方向决策已确认；进入 Step 4 Plan 前仍需完成 demo0 凭据脱敏 mini-task，并在 Step 3 架构设计中确认候选目录和 API 边界。**
