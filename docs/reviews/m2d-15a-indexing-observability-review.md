# M2D-15A Indexing Observability Review

## Scope

- `M2D-15A` stays narrowly scoped to indexing job observability and runtime state fidelity.
- This branch adds:
  - durable runtime sidecar state via `knowledge_ingest_job_runtime_states`
  - fine-grained ingest steps for parser and runtime stages
  - shared `IndexingProgressUpdater`
  - parser progress wiring in `IndexingAdminService`
  - embedding batch progress metrics in `EmbeddingBatchService` and runner
  - expanded admin job summary fields
  - minimal Knowledge Jobs panel progress display
- This branch does not add:
  - worker queue
  - SSE / WebSocket
  - new progress page
  - retrieval / rerank / answer changes
  - NL chat integration
  - console redesign

## Acceptance Outcome

- `M2D-15A` is accepted after implementation, targeted validation, real-PDF runtime acceptance, and acceptance hardening closure.
- Accepted real PDF validation facts:
  - file: `智能风控实践指南.pdf`
  - path: `/Users/zhengli/Desktop/workspace/CHORD-local-test-docs/智能风控实践指南.pdf`
  - file size: `26,482,250 bytes`
  - page count: `253`
  - version id: `item_real_pdf_v1`
  - job id: `idxjob_fe745427648643698375de98910677c7`
  - manifest id: `idx_item_real_pdf_v1_de98910677c7`
  - total duration: `575.880s`
  - `chunk_count = 1139`
  - `embedding_count = 1139`
  - `vector_mapping_count = 1139`
  - `embedding_batch_count = 114`
  - `embedding_batches_completed = 114`
  - `parser_duration_ms = 493503`
  - `embedding_duration_ms = 79941`
  - `faiss_duration_ms = 335`
  - `total_duration_ms = 575880`

## Implementation Notes

- Durable state remains split:
  - `knowledge_ingest_jobs` stores lifecycle truth and manifest pointers
  - `knowledge_ingest_job_runtime_states` stores additive observability metrics
- Redis remains the live mirror for high-frequency progress updates.
- `IndexingAdminService` now owns parser-stage progress because parsing still happens before runner execution.
- `IndexingJobRunner` reuses the same `IndexingProgressUpdater`, so users can observe one continuous job across parser, chunking, embedding, FAISS, and activation stages.
- Failure semantics now preserve the actual failing stage in `current_step`, while `status=failed` remains the terminal lifecycle fact.

## Observed Progress Snapshots

- `t+0s`: `runtime_current_step=parsing_pdf`, `progress_message=parsing document`
- `t+5s`: `current_step=ocr_running`, `progress_message=OCR started`
- `t+231s`: `current_step=ocr_running`, `progress_message=OCR finished`
- `t+484s`: `current_step=text_merging`, `progress_message=Text merged`
- `t+495s`: `current_step=embedding`, `progress_message=embedding batch 0 / 114`
- `t+500s`: `progress_message=embedding batch 8 / 114`
- `t+515s`: `progress_message=embedding batch 29 / 114`
- `t+540s`: `progress_message=embedding batch 70 / 114`
- `t+567s`: `progress_message=embedding batch 114 / 114`
- `t+575s`: `status=completed`, `current_step=completed`, `progress_message=manifest activated`

## Acceptance Hardening Closure

- `page_count` propagation is now closed:
  - admin job summary now surfaces `page_count`
  - extraction prefers parser metadata, then parsed chunk page ranges, then safe PDF fallbacks
  - page-count extraction failure does not fail the indexing job
- parser early failure durable state is now closed:
  - early parser exceptions set durable `status=failed`
  - `current_step` remains the real failing stage such as `parsing_pdf`
  - `error_message` and `progress_message` stay populated
  - durable terminal timestamps and runtime sidecar state are flushed during the failure path

## Validation

- Targeted tests passed:
  - `tests/knowledge_base/test_schemas.py`
  - `tests/knowledge_base/test_sqlalchemy_repositories.py`
  - `tests/knowledge_base/test_services.py`
  - `tests/risk_knowledge/ingestion/test_swxy_parser_progress.py`
  - `tests/risk_knowledge/embedding/test_embedding_runtime.py`
  - `tests/risk_knowledge/admin/test_indexing_admin_service.py`
  - `tests/risk_knowledge/admin/test_admin_api_routes.py`
  - `tests/risk_knowledge/runtime/test_indexing_job_runner.py`
  - `tests/risk_knowledge/runtime/test_indexing_orchestrator.py`
  - `tests/risk_knowledge/runtime/test_redis_task_state.py`
  - `tests/frontend/test_risk_knowledge_ui_console.py`
- Result:
  - `68 passed, 3 skipped`
- Real runtime acceptance passed for the accepted 253-page PDF:
  - external polling no longer stayed only at coarse `queued/running`
  - observed parser-stage progress included `parsing_pdf`, `ocr_running`, and `text_merging`
  - observed embedding sub-progress included batch progress through `114 / 114`
  - final completion metrics matched: `chunk_count = embedding_count = vector_mapping_count = 1139`
- Retrieval validation passed:
  - `什么是多头借贷风险？` -> `candidate_count=5`
  - `贷前风控主要关注哪些风险信号？` -> `candidate_count=5`
  - `风控策略如何识别欺诈风险？` -> `candidate_count=5`

## Residual Observation

- `layout_analyzing` and `table_analyzing` were not captured in the accepted polling run.
- This remains non-blocking for `M2D-15A` because parser progress, OCR progress, text merge progress, embedding batch progress, completion metrics, and failure-state fidelity were all validated on the real long-running PDF.

## Remaining Non-Scope

- `M2D-15B` worker queue remains a separate phase.
- Production cost / timeout / retry policy remains a separate phase.
- Advanced console / progress-stream UX remains a separate phase.
- No worker queue was added in `M2D-15A`.
- No SSE / WebSocket was added in `M2D-15A`.
- No retrieval / rerank / answer changes were made in `M2D-15A`.
- No `M2D-15D` console redesign was started in `M2D-15A`.
