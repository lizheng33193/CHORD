# M2A-Runtime Quality Plan

## Goal

`M2A` 与 `M2A-Verify Seed Patch 1/1.1` 已完成，下一阶段进入 `M2A-Runtime Quality`。

本阶段目标不是进入 `M2B`，也不是继续做 seed 扩写，而是在不扩大架构复杂度的前提下，收敛已经明确暴露的运行时质量问题：

- unresolved placeholder 未被 Safety Gate 稳定拦截
- deterministic retriever 存在 table-level false positive
- SQL example / few-shot 对模型风格牵引过强
- structured output fallback 不稳

目标产出：

- Data Agent SQL 生成链路更安全
- prompt context 更稳、更少误召回
- structured output 错误更可解释、更可控

## Hard Boundaries

本阶段明确不做：

- vector DB / embedding / reranker / rerank
- `query_data` 接入 `M2A`
- `M1 SQL HITL` 状态机改造
- `M1.5 Orchestrator Bridge` artifact contract 改造
- public `GenerateRequest` 透传 `knowledge_context`
- `approve / edit / revise / reject / execute` 权限边界改造

本阶段必须保持：

- `DataAgentService.create_run()` / `revise_run()` 仍是显式 Data Agent 入口
- `revise_run` retrieval 继承现有 run 的 `run_type / output_bucket / country / project_id`
- 结构化输出失败与 Safety Gate blocked 明确区分

## Six Sub-Stages

### RQ-0 文档与基线

- 新增 runtime quality plan 与 baseline review
- 更新 `PLANNING.md` 与 `TASK.md`
- 验证：`git diff --check`

### RQ-1 Safety Gate unresolved placeholder

新增 `UNRESOLVED_PLACEHOLDER` 检测规则，拦截：

- `<target_users>`、`<table_name>`、`<start_date>`
- `{name}`、`{{name}}`、`${name}`
- `TODO`、`TBD`、`PLACEHOLDER`、`replace_me`
- `your_table`、`some_table`、`xxx_here`

同时必须避免误杀正常 SQL 比较：

- `amount < 100`
- `dt > '2026-01-01'`

验收：

- placeholder SQL `safety_status=blocked`
- 正常 `SELECT` 不误杀
- 被 blocked 的 SQL 不可 approve/execute

推荐验证：

- `python -m compileall -q app tests`
- `pytest tests/data_agent/test_api.py -q`
- 如新增 direct safety tests：`pytest tests/data_agent/test_safety.py -q`

### RQ-2 Retriever false positive 收敛

只在 deterministic retriever 内收紧 scoring，不引入新检索架构。

重点规则：

- `run_type` 参与 `sql_examples` / `error_cases` 初筛
- `output_bucket` 参与 writeback example/error case 初筛
- glossary 的 `mapped_tables / mapped_fields` 权重高于普通文本命中
- 单弱关键词不足以让 table 进入 top-k
- unrelated bucket / unrelated run_type 增加惩罚分
- pure `query_only` high-risk cohort 请求不召回 writeback examples
- combo writeback 请求仍允许召回 behavior glossary/table/example

验收：

- `mx high-risk cohort` 不再误召回 behavior writeback example 或弱相关 behavior table
- `mx behavior writeback` 仍召回 `example:behavior-writeback`
- `ph` query 不串到 `mx` 专属 error case

推荐验证：

- `pytest tests/data_knowledge/test_data_knowledge_retriever.py -q`
- `pytest tests/data_agent/test_api.py -q`

### RQ-3 SQL example / few-shot 风格控制

继续保持摘要型 example，不恢复 full SQL 注入。

Prompt context 中固定加入：

- use as pattern guidance, not literal SQL
- adapt tables / fields / filters / dates to current request
- do not copy example WHERE clauses unless semantically matching

behavior writeback 还需固定：

- define target cohort first
- join behavior source by `uid`
- return `uid` plus requested behavior fields
- do not scan behavior table without cohort/uid constraint

验收：

- prompt context 中出现 pattern guidance
- 保留 writeback 的 cohort-first 安全约束
- 不重新暴露完整 SQL 原文

推荐验证：

- `pytest tests/data_knowledge/test_data_knowledge_retriever.py -q`
- `pytest data_acquisition_agent/tests/test_prompt_assembler.py -q`
- 如新增：`pytest tests/data_knowledge/test_prompt_context.py -q`

### RQ-4 Structured output fallback

只改 `data_acquisition_agent/orchestrator.py` 的 structured output 处理，不改 public route shape。

目标流程：

1. strip markdown fences
2. 提取首个可信 JSON object
3. 对关键字段做最小 normalize
4. 再走现有 schema 校验

失败分层：

- fenced JSON / 前后夹杂说明文字：尽量修复并继续
- 缺字段 / 类型不对 / 非 JSON：受控失败

失败语义必须固定：

- Safety Gate blocked：已有 SQL，可落 `DataAgentRun + SQLVersion`
- structured output unrecoverable：没有可靠 SQL
  - `create_run -> HTTP 422`，不创建 run
  - `revise_run -> HTTP 422`，不创建新 version，旧 run 不变

错误响应必须：

- 返回稳定 machine-readable error code
- 只返回摘要化信息
- 不暴露 raw LLM output / prompt /内部 knowledge context

推荐验证：

- `pytest data_acquisition_agent/tests/test_orchestrator.py -q`
- `pytest data_acquisition_agent/tests/test_prompt_assembler.py -q`
- `pytest tests/data_agent/test_api.py -q`

### RQ-5 回归与结果文档

- 新增 `docs/reviews/m2a-runtime-quality-results.md`
- 更新 `PLANNING.md` 与 `TASK.md`
- 记录四类问题的修复前后差异、剩余风险、是否满足进入 `M2B` 条件

推荐回归：

- `python -m compileall -q app data_acquisition_agent tests`
- `pytest tests/auth/test_seed.py tests/auth/test_permissions.py tests/data_knowledge/test_data_knowledge_service.py tests/data_knowledge/test_data_knowledge_api.py tests/data_knowledge/test_data_knowledge_retriever.py tests/data_agent/test_api.py data_acquisition_agent/tests/test_prompt_assembler.py data_acquisition_agent/tests/test_orchestrator.py -q`

## Entry Criteria For M2B

只有以下条件满足后，才考虑进入 `M2B`：

1. placeholder 能被 Safety Gate 拦截
2. `mx high-risk cohort` 不再明显误召回 behavior writeback
3. behavior writeback 仍稳定召回正确 example
4. prompt context 不再明显诱导复制 example
5. structured output 错误有 fallback 或可解释失败
6. Round 1 / Seed Patch 1 暴露的 runtime 问题已完成复测
