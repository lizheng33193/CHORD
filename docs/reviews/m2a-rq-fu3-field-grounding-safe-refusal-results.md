# M2A-RQ-FU3 Field Grounding & Safe Refusal Results

## Scope

本轮 `M2A-RQ-FU3` 只处理两类 runtime follow-up：

1. stronger field grounding with warning-only unsupported-field risk
2. normalize under-specified `bucket_writeback` refusal into a Data Agent specific `422`

本轮不改：

- `GenerateRequest` / `GenerateResponse` schema
- `data_acquisition_agent/orchestrator.py`
- `M1` SQL HITL 状态机
- `M1.5` Orchestrator Bridge
- `query_data`
- retriever scoring 大结构
- seed assets
- vector retrieval / embedding / rerank

## Implemented Changes

### 1. Prompt-side field grounding

`app/data_knowledge/prompt_context.py` 现已新增 `retrieved_field_grounding` section：

- 输出当前 retrieved catalog/glossary 支撑的 `table -> allowed_fields`
- 明确写入：
  - selected table fields must come from retrieved catalog/glossary
  - do not switch to a historical alias family unless grounded
  - do not invent new base-table fields from historical examples

`data_acquisition_agent/prompt_assembler.py` 也已同步把 field grounding 提升为全局 Data Agent retrieved-context 规则。

### 2. Warning-only unsupported-field risk

`app/data_agent/service.py` 现已在 SQL generation 后追加保守的 unsupported-field risk 检查：

- 只标高置信 base-table field
- 支持：
  - `alias.field`
  - 单表 SQL 的 unqualified field
- 不标：
  - 多表歧义字段
  - CTE 输出字段
  - `SELECT AS` 派生字段
  - 聚合 / 窗口别名
  - 子查询输出字段

风险输出：

- `category = UNSUPPORTED_FIELD`
- `risk_level = medium`
- 落在现有 `safety_result.warnings`

当前仍是 warning-only：

- 不改变 `safety_status`
- 不触发 blocked
- 不改变 approve / execute 状态机

### 3. Safe refusal normalization

`app/data_agent/service.py` 现已新增 under-specified `bucket_writeback` 识别，并把对应的 structured-output failure 归一为：

- `DATA_AGENT_WRITEBACK_REQUIRES_COHORT`

对外 detail 结构固定为：

- `code = DATA_AGENT_WRITEBACK_REQUIRES_COHORT`
- `stage = data_agent_sql_generation`
- `reason = Writeback requests require an explicit uid list or cohort conditions before SQL generation.`
- `retriable = true`

当前保持：

- create：`HTTP 422`，不创建 run / version
- revise：`HTTP 422`，不创建新 version，不改 current SQL / approved hash / run status

同时保留原有语义分层：

- `SCHEMA_VALIDATION_FAILED`：真实 structured output schema 坏掉
- `SQL_GENERATION_REQUIRED`：普通 non-SQL generation result
- `DATA_AGENT_WRITEBACK_REQUIRES_COHORT`：under-specified `bucket_writeback`

## Verification

### Targeted tests

- `python -m compileall -q app data_acquisition_agent tests`
- `pytest tests/data_knowledge/test_prompt_context.py data_acquisition_agent/tests/test_prompt_assembler.py tests/data_agent/test_api.py -q`

结果：

- `38 passed`

### Regression subset

- `pytest tests/data_knowledge/test_data_knowledge_retriever.py data_acquisition_agent/tests/test_orchestrator.py tests/data_knowledge/test_prompt_context.py data_acquisition_agent/tests/test_prompt_assembler.py tests/data_agent/test_api.py -q`

结果：

- `59 passed`

### Repo checks

- `git diff --check`

结果：

- passed

## Live Rerun Samples

本轮复跑 3 条目标样例，使用真实 Data Agent create path + live LLM generation。

### 1. mx-high-risk-cohort

Request:

- `用 Data Agent 生成 SQL，查询最近 7 天高风险用户`

Observed result:

- `HTTP 201`
- `safety_status = passed`
- 无 `UNSUPPORTED_FIELD` warning

Observed SQL:

```sql
WITH recent_high_risk_applies AS (
    SELECT
        user_uuid,
        apply_create_at,
        risk_level
    FROM
        hive.dwd.dwd_w_apply
    WHERE
        CAST(apply_create_at AS DATETIME) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
        AND risk_level = 'high'
        AND dt >= DATE_FORMAT(DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY), '%Y%m%d')
        AND dt <= DATE_FORMAT(CURRENT_DATE(), '%Y%m%d')
)
SELECT DISTINCT
    user_uuid
FROM
    recent_high_risk_applies;
```

Assessment:

- historical field-family drift: still visible
- historical date/source drift: not obvious
- unsupported-field warning: none

Interpretation:

- 当前 retrieved grounding 仍可支撑 `user_uuid` / `apply_create_at` 这类字段，因此 FU3 不会把它们标成 unsupported
- 这说明 FU3 的保守 checker 没有误伤，但也说明仅靠 field support 还不能消除所有 field-family drift

Conclusion:

- `partial`

### 2. mx-behavior-writeback

Request:

- `用 Data Agent 补齐这些用户的 behavior 数据并写回 behavior`

Observed result:

- `HTTP 422`
- `code = DATA_AGENT_WRITEBACK_REQUIRES_COHORT`
- 不再表现成 `SCHEMA_VALIDATION_FAILED`

Assessment:

- under-specified refusal: normalized
- placeholder drift: not observed
- broad-scan drift: not observed

Interpretation:

- FU3 已把这类请求从通用 schema error 收口成 Data Agent 业务语义
- 当前对用户/前端/审计都更可解释

Conclusion:

- `pass`

### 3. mx-glossary-combo-writeback

Request:

- `找出墨西哥首贷且从未逾期的用户，并写回 behavior`

Observed result:

- `HTTP 201`
- `safety_status = passed`
- 出现多条 `UNSUPPORTED_FIELD` warning

Observed SQL 特征：

- 组合意图仍被保留
- 仍出现明显 historical template drift：
  - 固定日期 `20260201`
  - 固定 source filter `MEX017` / `MEXI` / `MEXICASH`
  - 模板式 behavior 字段列举

Observed warnings:

- `servertimestamp`
- `scenetype`
- `processtype`
- `extend`
- `clientmodel`
- `clientosversion`
- `url`
- `refer`
- `ip`
- `dt`
- `source`

Assessment:

- combo intent preserved: yes
- unsupported-field risk: now visible
- historical template drift: still significant

Interpretation:

- FU3 已经让 reviewer 能明确看到哪些 behavior fields 没有当前 retrieved grounding 支撑
- 但 combo writeback 仍明显回退到 historical template SQL，说明下一轮 follow-up 需要继续压 template drift，而不是马上进入 `M2B`

Conclusion:

- `still_needs_runtime_followup`

## Overall Outcome

本轮 `M2A-RQ-FU3` 结论：

- field grounding：已从“纯 prompt”提升为“prompt + warning-only risk”
- unsupported-field：已可观测、可审计
- under-specified writeback：已不再表现成 `SCHEMA_VALIDATION_FAILED`
- combo writeback historical template drift：仍未完全收口

整体状态：

- `still_needs_runtime_followup`

## Recommendation

当前仍不建议直接进入 `M2B`。

更合理的下一步是继续一个更窄的 runtime follow-up，重点放在：

1. combo writeback 的 anti-template drift
2. current request / retrieved grounding 与 historical behavior template 之间的优先级进一步拉开
3. 如需继续提高 field-quality gate，再评估是否把高置信 unsupported base-table field 从 warning 升级到更强约束
