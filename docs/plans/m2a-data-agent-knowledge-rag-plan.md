# M2A Data Agent Knowledge RAG Plan

## Summary

M2A 分 5 个小阶段实施，始终保持：

- 不改 orchestrator `query_data`
- 不改 M1 SQL HITL 状态机
- 不改 M1.5 artifact contract
- 不开放 public `retrieved_context`
- 不绕过 Safety Gate / human review / execute 权限

## M2A-0

- 新增 design doc
- 新增 plan doc
- 更新 `PLANNING.md`
- 更新 `TASK.md`
- 新增 `data:knowledge:read/write/manage`
- 更新角色 seed
- 补权限测试

## M2A-1

- 实现 `app/data_knowledge/models.py`
- 实现 repository/service/api
- 新增 `data_knowledge_seed/`
- 实现 seed importer
- 接入 `create_auth_schema()`
- 做最小 CRUD API 与 SQL 明文 redaction

## M2A-2

- 实现 deterministic retriever
- 实现 `RetrievedKnowledgeContext`
- 实现 prompt context assembler
- 固定 country/project precedence 与 top-k 截断

## M2A-3

- `DataAgentService.create_run()` 接 retriever
- `DataAgentService.revise_run()` 接 retriever
- `DataAcquisitionOrchestrator.generate(..., retrieved_context=None)`
- `prompt_assembler` 注入 retrieved section
- `data_agent_sql_versions.retrieval_snapshot_json`

## M2A-4

- approved + executed success -> draft SQL example
- execute failure -> open error case
- revise after failure -> update/resolve error case
- retriever 只召回 active examples

## Required Verification

- auth seed / permission tests
- data knowledge API tests
- seed importer idempotency tests
- retriever precedence tests
- prompt context trimming tests
- create_run/revise_run integration tests
- example/error case SQL redaction tests
- M1/M1.5 regression tests
