# M2D-15A Indexing Job Observability & Runtime State Fidelity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make long-running indexing jobs expose truthful stage, progress, and runtime metrics through MySQL, Redis, admin APIs, and the existing Knowledge Jobs panel.

**Architecture:** Keep MySQL as the durable lifecycle truth and Redis as the live mirror, then add one additive durable runtime sidecar plus a shared `ProgressUpdater` that spans parser, runner, embedding, and terminal state updates. Preserve the current call graph by wiring parser progress in `IndexingAdminService` before control passes into `IndexingJobRunner`.

**Tech Stack:** FastAPI admin API, SQLAlchemy, MySQL, Redis, SWXY parser adapter, DashScope/OpenAI-compatible embeddings, FAISS, existing dashboard-side React Knowledge Console.

---

## Summary

This plan implements `M2D-15A` only.

Locked non-scope:

- no worker queue or `M2D-15B`
- no SSE / WebSocket
- no retrieval / rerank / answer changes
- no `M2D-15D` console redesign

Accepted baseline facts that this plan must preserve and surface:

- real PDF: `253 pages`
- file size: `26.48MB`
- total duration: about `10m12s`
- `chunk_count = 1139`
- `embedding_count = 1139`
- `vector_mapping_count = 1139`
- manifest id: `idx_item_real_pdf_v1_8a5117977e31`

## File Structure

Primary files expected to change in the later implementation PR:

- Modify: `app/knowledge_base/schemas.py`
- Modify: `app/knowledge_base/models.py`
- Modify: `app/knowledge_base/repositories/interfaces.py`
- Modify: `app/knowledge_base/repositories/sqlalchemy.py`
- Modify: `app/knowledge_base/services/ingest_job_service.py`
- Modify: `app/risk_knowledge/runtime/schemas.py`
- Modify: `app/risk_knowledge/runtime/redis_state.py`
- Create: `app/risk_knowledge/runtime/progress_updater.py`
- Modify: `app/risk_knowledge/runtime/runner.py`
- Modify: `app/risk_knowledge/runtime/orchestrator.py`
- Modify: `app/risk_knowledge/admin/indexing_admin_service.py`
- Modify: `app/risk_knowledge/ingestion/swxy_parser_adapter.py`
- Modify: `app/risk_knowledge/embedding/batch_service.py`
- Modify: `app/risk_knowledge/admin/schemas.py`
- Modify: `app/api/risk_knowledge_admin.py`
- Modify: `app/static/js/components/panels/knowledge/KnowledgeVersionJobsPanel.jsx`
- Modify: `app/static/js/components/panels/knowledge/KnowledgeBaseConsole.jsx`

Primary tests expected in the later implementation PR:

- Modify: `tests/knowledge_base/test_schemas.py`
- Modify: `tests/knowledge_base/test_sqlalchemy_repositories.py`
- Modify: `tests/knowledge_base/test_services.py`
- Modify: `tests/risk_knowledge/runtime/test_redis_task_state.py`
- Modify: `tests/risk_knowledge/runtime/test_indexing_job_runner.py`
- Modify: `tests/risk_knowledge/runtime/test_indexing_orchestrator.py`
- Add: `tests/risk_knowledge/ingestion/test_swxy_parser_progress.py`
- Modify: `tests/risk_knowledge/embedding/test_embedding_runtime.py`
- Modify: `tests/risk_knowledge/admin/test_indexing_admin_service.py`
- Modify: `tests/risk_knowledge/admin/test_admin_api_routes.py`
- Modify: `tests/frontend/test_risk_knowledge_ui_console.py`

## Task 1: Durable Progress Contract And Storage

**Files:**
- Modify: `app/knowledge_base/schemas.py`
- Modify: `app/knowledge_base/models.py`
- Modify: `app/knowledge_base/repositories/interfaces.py`
- Modify: `app/knowledge_base/repositories/sqlalchemy.py`
- Modify: `app/knowledge_base/services/ingest_job_service.py`
- Modify: `app/risk_knowledge/runtime/schemas.py`

- [ ] Expand job step taxonomy to support observable parser/runtime stages without changing endpoint names.
- [ ] Keep `knowledge_ingest_jobs` as durable lifecycle truth for `status`, `current_step`, `error_message`, heartbeat, and manifest ids.
- [ ] Add one additive durable sidecar table `knowledge_ingest_job_runtime_states` keyed by `job_id`.
- [ ] Persist additive observability payload in the sidecar table:
  - `progress_message`
  - `progress_completed_steps`
  - `progress_total_steps`
  - `file_size_bytes`
  - `page_count`
  - `chunk_count`
  - `embedding_count`
  - `embedding_batch_count`
  - `embedding_batches_completed`
  - `vector_mapping_count`
  - `parser_duration_ms`
  - `embedding_duration_ms`
  - `faiss_duration_ms`
  - `total_duration_ms`
- [ ] Preserve failure semantics:
  - `status=failed`
  - `current_step=<actual failing stage>`
  - do not collapse `current_step` to generic `failed`

## Task 2: Shared ProgressUpdater With Throttled Durable Writes

**Files:**
- Create: `app/risk_knowledge/runtime/progress_updater.py`
- Modify: `app/risk_knowledge/runtime/redis_state.py`
- Modify: `app/risk_knowledge/runtime/schemas.py`
- Modify: `app/risk_knowledge/admin/indexing_admin_service.py`
- Modify: `app/risk_knowledge/runtime/runner.py`

- [ ] Introduce one shared `ProgressUpdater` abstraction reused by admin-service parsing and runner-owned downstream stages.
- [ ] Define Redis vs MySQL write behavior:
  - Redis may update at high frequency
  - MySQL durable updates are throttled
- [ ] Support `force=True` for:
  - stage transitions
  - terminal `completed`
  - terminal `failed`
- [ ] Throttle non-forced durable updates by:
  - elapsed interval such as `2-5s`
  - meaningful metric change
  - embedding batch progress checkpoint
- [ ] Always flush terminal state so that Redis loss does not hide the final outcome.

## Task 3: Parser Progress Wiring In The Current Call Graph

**Files:**
- Modify: `app/risk_knowledge/admin/indexing_admin_service.py`
- Modify: `app/risk_knowledge/ingestion/swxy_parser_adapter.py`

- [ ] Keep document parsing inside `IndexingAdminService._run_job()`.
- [ ] Build the shared `ProgressUpdater` before invoking `SwxyParserAdapter.parse(...)`.
- [ ] Pass a callback from `IndexingAdminService` into `SwxyParserAdapter.parse(...)`.
- [ ] Map parser messages to observable steps:
  - parse entry -> `parsing_document` or `parsing_pdf`
  - `OCR started` -> `ocr_running`
  - `Layout analysis` -> `layout_analyzing`
  - `Table analysis` -> `table_analyzing`
  - `Text merged` -> `text_merging`
  - parser completion -> `chunking`
- [ ] Capture parser-side facts for later durable metrics:
  - `file_size_bytes`
  - `page_count` when available
  - `parser_duration_ms`

## Task 4: Runner, Embedding, And FAISS Observability

**Files:**
- Modify: `app/risk_knowledge/runtime/runner.py`
- Modify: `app/risk_knowledge/runtime/orchestrator.py`
- Modify: `app/risk_knowledge/embedding/batch_service.py`

- [ ] Reuse the same `ProgressUpdater` after control enters orchestrator/runner.
- [ ] Keep stage progress separate from embedding sub-progress.
- [ ] Use `progress_completed_steps / progress_total_steps` only for top-level pipeline stage movement.
- [ ] Add embedding-stage sub-progress:
  - `embedding_batch_count`
  - `embedding_batches_completed`
- [ ] Emit embedding progress messages like `embedding batch 31 / 114`.
- [ ] Record durable counts:
  - `chunk_count`
  - `embedding_count`
  - `vector_mapping_count`
- [ ] Record durations:
  - `embedding_duration_ms`
  - `faiss_duration_ms`
  - `total_duration_ms`
- [ ] Ensure completed jobs surface `chunk_count = embedding_count = vector_mapping_count`.

## Task 5: Admin API Summary Merge And Minimal UI Enhancement

**Files:**
- Modify: `app/risk_knowledge/admin/schemas.py`
- Modify: `app/risk_knowledge/admin/indexing_admin_service.py`
- Modify: `app/api/risk_knowledge_admin.py`
- Modify: `app/static/js/components/panels/knowledge/KnowledgeVersionJobsPanel.jsx`
- Modify: `app/static/js/components/panels/knowledge/KnowledgeBaseConsole.jsx`

- [ ] Preserve current admin endpoints and polling behavior.
- [ ] Expand job summary/list responses with additive observability fields:
  - `file_size_bytes`
  - `page_count`
  - `chunk_count`
  - `embedding_count`
  - `embedding_batch_count`
  - `embedding_batches_completed`
  - `vector_mapping_count`
  - `elapsed_seconds`
  - `parser_duration_ms`
  - `embedding_duration_ms`
  - `faiss_duration_ms`
  - `total_duration_ms`
- [ ] Keep merge behavior stable:
  - use Redis live state for active jobs when available
  - fall back to durable MySQL job + sidecar state otherwise
- [ ] Limit frontend changes to the existing jobs panel:
  - current step
  - progress message
  - stage progress
  - embedding batch progress
  - timing fields
  - lightweight count display
- [ ] Do not add a new page or redesign the console.

## Task 6: Tests And Acceptance

**Files:**
- Modify: `tests/knowledge_base/test_schemas.py`
- Modify: `tests/knowledge_base/test_sqlalchemy_repositories.py`
- Modify: `tests/knowledge_base/test_services.py`
- Modify: `tests/risk_knowledge/runtime/test_redis_task_state.py`
- Modify: `tests/risk_knowledge/runtime/test_indexing_job_runner.py`
- Modify: `tests/risk_knowledge/runtime/test_indexing_orchestrator.py`
- Add: `tests/risk_knowledge/ingestion/test_swxy_parser_progress.py`
- Modify: `tests/risk_knowledge/embedding/test_embedding_runtime.py`
- Modify: `tests/risk_knowledge/admin/test_indexing_admin_service.py`
- Modify: `tests/risk_knowledge/admin/test_admin_api_routes.py`
- Modify: `tests/frontend/test_risk_knowledge_ui_console.py`

- [ ] Add coverage for detailed stage taxonomy and sidecar persistence.
- [ ] Verify parser progress wiring works while parsing still lives in `IndexingAdminService`.
- [ ] Verify throttled durable updates still flush terminal `completed/failed`.
- [ ] Verify failure semantics preserve the true failing step.
- [ ] Verify embedding sub-progress is separate from top-level stage progress.
- [ ] Verify API responses contain the new additive fields without route changes.
- [ ] Verify the existing jobs panel renders progress text and lightweight metrics.
- [ ] Run targeted acceptance commands for the later implementation PR:
  - `pytest -q tests/knowledge_base/test_schemas.py tests/knowledge_base/test_sqlalchemy_repositories.py tests/knowledge_base/test_services.py`
  - `pytest -q tests/risk_knowledge/runtime/test_redis_task_state.py tests/risk_knowledge/runtime/test_indexing_job_runner.py tests/risk_knowledge/runtime/test_indexing_orchestrator.py`
  - `pytest -q tests/risk_knowledge/embedding/test_embedding_runtime.py tests/risk_knowledge/admin/test_indexing_admin_service.py tests/risk_knowledge/admin/test_admin_api_routes.py`
  - `pytest -q tests/frontend/test_risk_knowledge_ui_console.py`
  - `python -m compileall -q app/risk_knowledge app/knowledge_base tests/risk_knowledge tests/knowledge_base tests/frontend`
  - `git diff --check`

## Acceptance Criteria

The later implementation PR is accepted only if:

- real PDF polling no longer stays at only `queued/running` for most of the job lifecycle
- API exposes meaningful `current_step` and `progress_message`
- OCR / layout / table / merge progress is visible
- embedding batch progress is visible
- `chunk_count = embedding_count = vector_mapping_count` on completed jobs
- failed jobs reveal the failing stage
- no worker queue, SSE / WebSocket, retrieval/rerank/answer work, or console redesign is introduced

