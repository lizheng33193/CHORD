# M2D-15 Production Hardening Final Review

## Historical Positioning

- this document is a historical stage review for `M2D-15 Final Production Hardening` only
- it records what landed in that slice and what remained out of scope at that time
- it must not be read as evidence that the later `M2D / Pre-M3` system-level final acceptance is complete
- later `PR-A / PR-B / PR-C` runtime gates plus the `codex/pre-m3-final-acceptance-closure` branch define the current system-level acceptance truth
- current system-level truth is:
  - core runtime hardening landed
  - final acceptance remains blocked by full-repository regression failures
  - Pre-M3 gates are not ready for M3 entry

## Scope

- 完成 durable async indexing execution：
  - API enqueue 仅创建 durable `queued` job
  - single-process worker loop 负责 claim / execute queued jobs
  - worker manager 接入 FastAPI startup / shutdown lifecycle
  - `risk_knowledge_indexing_worker_enabled` 支持测试与本地关闭 auto-start
- 完成 durable job control：
  - lease owner / lease expiry durable persistence
  - progress-driven heartbeat 续租
  - stale running job 标记并 requeue
  - queued cancel 与 running cooperative cancel request
- 完成 admin operations：
  - list jobs / get job detail
  - retry failed job -> 创建新 job
  - rebuild version -> 创建新 job 且生成新 manifest
  - cancel queued/running job
  - artifact cleanup dry-run-first
- 完成 guard rails：
  - file size / page count / chunk count / embedding batch count / runtime seconds
  - 全部统一走 `fail_job + ProgressUpdater` 失败路径
- 完成 artifact governance：
  - manifest artifact paths 记录到 job artifact registry
  - cleanup 保护 active manifest / version upload / managed roots boundary
  - temporary `.tmp` artifacts 可被 dry-run 列出
- 完成 minimal UI：
  - Retry failed
  - Rebuild index
  - Cancel queued/running
  - guard failure / stale / lease / heartbeat / cancel requested 展示

## Tests

- `pytest -q tests/risk_knowledge/admin/test_indexing_admin_service.py -k 'file_size_guard or page_count_guard'`
- `pytest -q tests/risk_knowledge/runtime/test_indexing_orchestrator.py`
- `pytest -q tests/risk_knowledge/runtime/test_progress.py tests/risk_knowledge/runtime/test_indexing_orchestrator.py tests/risk_knowledge/admin/test_artifact_cleanup_service.py tests/knowledge_base/test_services.py`
- `pytest -q tests/knowledge_base tests/risk_knowledge -k 'not swxy_default_chunker_loads and not dashscope_provider_requires_api_key'`
- `pytest -q tests/frontend/test_risk_knowledge_ui_console.py`

## Smoke

- small PDF indexing:
  - worker `run_once()` picked queued job
  - job completed
  - heartbeat present
  - active manifest created
- retry failed parser job:
  - initial job failed with parser error
  - retry created a new job
  - retry job completed
- rebuild successful version:
  - rebuild job completed
  - active manifest changed to a new manifest id
- cancel queued job:
  - queued cancel returned `canceled`
- guard exceed:
  - file size guard failed fast before parser
  - job status became `failed`
- artifact cleanup dry-run:
  - active uploads/manifests protected
  - temporary artifact listed as candidate
- retrieval debug:
  - deterministic retriever smoke returned indexed chunks from the newly activated manifest

## Residual Limitations

- worker remains single-process and non-distributed
- running cancel remains cooperative cancel only
- stale recovery remains full-job rerun, not checkpoint resume
- cleanup validation emphasizes dry-run safety over broad real-delete coverage
- full targeted backend suite still has 2 pre-existing environment-sensitive failures:
  - `tests/risk_knowledge/ingestion/test_swxy_parser_dependencies.py::test_swxy_default_chunker_loads`
    - missing local `tika` dependency
  - `tests/risk_knowledge/reranking/test_dashscope_provider.py::test_dashscope_provider_requires_api_key`
    - environment-provided DashScope config defeats the “missing api key” assumption

## Preserved Non-Goals

- no Celery / RQ / Kafka
- no SSE / WebSocket
- no distributed multi-node worker
- no retrieval / rerank / answer contract expansion
- no NL chat integration changes
- no admin console redesign
- no Java auto-installation
