# M2A Data Agent Knowledge RAG Design

## Goal

在不改变 M1 SQL HITL 与 M1.5 Orchestrator Bridge 边界的前提下，只增强显式 Data Agent 路径的 SQL 生成质量。

本阶段固定只接：

- `DataAgentService.create_run()`
- `DataAgentService.revise_run()`

不接：

- orchestrator `query_data`
- auto approve / auto execute
- public `retrieved_context`
- vector DB / embedding / reranker / 管理 UI

## Runtime Shape

目标链路：

`DataAgentService.create_run()/revise_run() -> DataKnowledgeRetriever -> PromptContextAssembler -> DataAcquisitionOrchestrator.generate(..., retrieved_context=...) -> SQL Safety Gate -> SQLReviewCard -> approve/edit/revise/reject/execute`

核心原则：

1. M2A 只增强生成质量，不改变执行权力。
2. retrieval context 只能由系统内部生成。
3. SQL 明文继续受 `data:query:view_sql` 保护。
4. approved SQL example 默认 `draft`，retriever 只召回 `active` examples。
5. retrieval snapshot version-scoped，只存不显。

## Data Knowledge Store

新增 `app/data_knowledge/` 领域模块，首版资产表：

- `data_catalog_tables`
- `data_catalog_fields`
- `data_glossary_terms`
- `data_sql_examples`
- `data_sql_error_cases`

状态枚举拆分：

- `KnowledgeAssetStatus = draft | active | deprecated`
- `ErrorCaseStatus = open | resolved | deprecated`

通用字段：

- `project_id`
- `country`
- `status`
- `source_type`
- `source_namespace`
- `source_key`
- `source_hash`
- `created_by`
- `updated_by`
- `created_at`
- `updated_at`

`source_type`：

- `seed`
- `manual`
- `approved_sql`
- `error_case`

## Seed Import

Seed 目录：

- `data_knowledge_seed/mx/`
- `data_knowledge_seed/ph/`
- `data_knowledge_seed/common/`

首版支持：

- `catalog.yaml`
- `glossary.yaml`
- `sql_examples.yaml`

固定 `source_namespace` 规范：

- `seed/common/glossary`
- `seed/mx/catalog`
- `seed/mx/glossary`
- `seed/mx/sql_examples`
- `seed/ph/catalog`
- `seed/ph/glossary`
- `seed/ph/sql_examples`

导入 identity：

- 唯一定位：`source_namespace + source_key`
- 内容版本：`source_hash`

removed-row deprecation 只允许影响：

- 同 `source_type=seed`
- 同 `source_namespace`
- 同 `project_id`
- 同 `country`
- 同资产类型

## Permissions

新增权限：

- `data:knowledge:read`
- `data:knowledge:write`
- `data:knowledge:manage`

角色默认：

- `admin` / `data_admin`：`read/write/manage`
- `analyst`：`read`
- `viewer`：无 knowledge 权限

边界：

- 直接访问 `data-knowledge` API：要求 `data:knowledge:*`
- `create_run/revise_run` 内部 retrieval 不要求 `data:knowledge:read`
- examples/error cases 返回 SQL 明文时仍要求 `data:knowledge:read + data:query:view_sql`

## Retrieval

内部 `RetrievedKnowledgeContext` 包含：

- table hits
- field hits
- glossary hits
- active SQL example hits
- open error case hits
- retrieval metadata

输入：

- `natural_language_request`
- `project_id`
- `country`
- `run_type`
- `output_bucket`

优先级：

1. same project + same country
2. global project + same country
3. same project + common
4. global project + common

固定约束：

- 不允许跨国家召回
- `common` 仅指 `country is null`
- 只召回 `active` example
- 只召回 `open` error case

## Prompt Context

不修改 public `GenerateRequest` shape。

内部新增：

- `DataAcquisitionOrchestrator.generate(request, *, retrieved_context=None)`
- `prompt_assembler` 的 retrieved context section

Prompt 注入：

- 可用表与用途
- 关键字段与字段解释
- join key / grain / time field
- glossary 术语映射
- approved SQL 模式摘要
- 错误提醒
- `bucket_writeback` 的 `uid/output_bucket/output_format` 约束

无 context 时保持既有行为兼容，但不要求 byte-for-byte prompt 相等。

## Retrieval Snapshot

在 `data_agent_sql_versions` 新增：

- `retrieval_snapshot_json`

只存摘要，不存完整 final prompt。

摘要至少包含：

- `context_hash`
- `table_ids`
- `field_ids`
- `glossary_ids`
- `example_ids`
- `error_case_ids`
- `section_counts`
- `trimmed`
- `country`
- `project_id`

现有 `/api/data-agent/runs*` 不默认返回该字段。

## Case Memory

approved SQL example 自动沉淀条件：

- `query_only`
- safety passed
- approved
- executed successfully

自动写入后默认：

- `status = draft`
- `source_type = approved_sql`

error case：

- execute 失败时生成或更新
- 默认 `status = open`

后续 `revise_run()` 成功生成新 SQL 时，更新最近匹配的 open error case：

- `fix_summary`
- `fixed_sql_hash`
- `fixed_sql_text`
- `status = resolved`
