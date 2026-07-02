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

## Implementation Notes

- Durable state remains split:
  - `knowledge_ingest_jobs` stores lifecycle truth and manifest pointers
  - `knowledge_ingest_job_runtime_states` stores additive observability metrics
- Redis remains the live mirror for high-frequency progress updates.
- `IndexingAdminService` now owns parser-stage progress because parsing still happens before runner execution.
- `IndexingJobRunner` reuses the same `IndexingProgressUpdater`, so users can observe one continuous job across parser, chunking, embedding, FAISS, and activation stages.
- Failure semantics now preserve the actual failing stage in `current_step`, while `status=failed` remains the terminal lifecycle fact.

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

## Remaining Non-Scope

- `M2D-15B` worker queue remains a separate phase.
- Production cost / timeout / retry policy remains a separate phase.
- Advanced console / progress-stream UX remains a separate phase.
