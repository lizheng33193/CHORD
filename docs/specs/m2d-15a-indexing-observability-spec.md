# M2D-15A Indexing Job Observability & Runtime State Fidelity Spec

## Baseline

`M2D-15A` starts after `M2D-14C Targeted File-Type Validation` acceptance.

Accepted validation facts that motivate this phase:

- real PDF input: `253 pages`
- file size: `26.48MB`
- end-to-end indexing duration: about `10m12s`
- `chunk_count = 1139`
- `embedding_count = 1139`
- `vector_mapping_count = 1139`
- manifest id: `idx_item_real_pdf_v1_8a5117977e31`

Observed gap:

- the job really progressed through OCR, layout analysis, chunking, embedding, and FAISS build
- external API polling still showed coarse `queued/running` for too long
- users and admins could not tell whether the job was healthy, stalled, or nearing completion

## Scope

`M2D-15A` improves observability and state fidelity for long-running indexing jobs.

This phase covers:

- finer-grained indexing stage visibility
- accurate reconciliation between MySQL durable state and Redis runtime state
- parser callback progress exposure for PDF flows
- embedding batch sub-progress exposure
- durable indexing metrics for large-document analysis
- minimal enhancement of the existing Knowledge Jobs panel

This phase does not start:

- worker queue or `M2D-15B`
- SSE / WebSocket
- retrieval / rerank / answer changes
- `M2D-15D` console redesign
- production cost / timeout / retry policy redesign

## Runtime Ownership Model

State ownership remains fixed:

- MySQL durable state = final fact source
- Redis runtime state = live mirror for active jobs
- Admin API = merged summary view over durable and runtime state
- UI = polling-based display over the existing admin endpoints

Durable lifecycle truth stays on `knowledge_ingest_jobs`:

- `status`
- `current_step`
- `error_message`
- `started_at`
- `completed_at`
- `last_heartbeat_at`
- `latest_manifest_index_id`
- `active_manifest_index_id`

Additive observability data is planned for a new sidecar table:

- table: `knowledge_ingest_job_runtime_states`
- one row per `job_id`
- fields:
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

This additive table is preferred because the repo does not use a migration framework, and adding one new table is lower risk than broad `ALTER knowledge_ingest_jobs` work.

## Progress Model

`M2D-15A` keeps two distinct progress concepts.

Main stage progress:

- `progress_completed_steps / progress_total_steps`
- represents coarse pipeline progress only
- examples:
  - parsing
  - chunking
  - persisting chunks
  - embedding
  - FAISS build
  - manifest activation

Embedding sub-progress:

- `embedding_batches_completed / embedding_batch_count`
- used only inside the embedding stage
- does not change the meaning of `progress_total_steps`

Expected later UX shape:

- stage progress: `6 / 10`
- embedding batches: `31 / 114`

## Stage Taxonomy

The later implementation should move from coarse job steps to an observable taxonomy that still stays stable across APIs and UI:

- `queued`
- `parsing_document`
- `parsing_pdf`
- `ocr_running`
- `layout_analyzing`
- `table_analyzing`
- `text_merging`
- `chunking`
- `persisting_chunks`
- `embedding`
- `faiss_building`
- `manifest_persisting`
- `activating_manifest`
- `completed`

`failed` remains a job `status`, not the primary semantic value for `current_step`.

## Parser Progress Wiring

Current indexing flow parses inside `IndexingAdminService._run_job()` before `IndexingJobRunner` starts. Because of that, parser-stage progress cannot be owned only by runner if we want real PDF OCR/layout/table callbacks to surface.

Default `M2D-15A` implementation choice:

- keep `SwxyParserAdapter.parse(...)` in `IndexingAdminService`
- create one shared `ProgressUpdater`
- pass parser callback updates from `IndexingAdminService` into `SwxyParserAdapter.parse(...)`
- reuse the same updater when control moves into orchestrator and runner

This phase should not refactor parser ownership into runner unless a later spec explicitly changes runtime architecture.

## ProgressUpdater Contract

`M2D-15A` introduces one shared progress-writing contract for parser, runner, embedding, and terminal states.

ProgressUpdater responsibilities:

- normalize stage transitions
- write high-frequency live state to Redis
- write throttled durable progress to MySQL
- maintain `last_heartbeat_at`
- update counts, durations, and manifest ids
- force-flush terminal `completed` and `failed` states

Required semantics:

- `force=True` for stage transitions
- `force=True` for terminal writes
- non-forced metric updates are throttled
- durable writes occur only on:
  - stage changes
  - meaningful metric jumps
  - embedding batch interval updates
  - elapsed-time threshold such as every `2-5s`

## Failure Semantics

Failure behavior must preserve the real failing stage.

Required later runtime behavior:

- `status = failed`
- `current_step = <actual failing step>`
  - for example `layout_analyzing`, `embedding`, `faiss_building`
- `error_message = sanitized concrete error`
- `progress_message = failed during <step>: ...`

Do not overwrite `current_step` with generic `failed`. The generic terminal outcome is already represented by `status=failed`.

## Admin API Additions

The later implementation should keep the current admin endpoints and polling model while expanding response fields for job summary endpoints:

- `GET /api/risk-knowledge/admin/indexing-jobs/{job_id}`
- `GET /api/risk-knowledge/admin/indexing-jobs`

Existing fields to keep and improve:

- `status`
- `current_step`
- `progress_message`
- `progress_completed_steps`
- `progress_total_steps`
- `last_heartbeat_at`
- `latest_manifest_index_id`
- `active_manifest_index_id`
- `error_message`

Additive future fields:

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

Merge rule:

- if Redis runtime state exists for a live job, use it for live progress display
- otherwise fall back to durable MySQL job row plus durable sidecar row
- MySQL remains the final fact source for terminal lifecycle truth

## UI Boundary

`M2D-15A` is limited to the existing Knowledge Jobs panel.

Allowed later UI changes:

- show effective `current_step`
- show `progress_message`
- show stage progress
- show embedding batch sub-progress
- show `last_heartbeat_at`, `started_at`, `completed_at`, `elapsed_seconds`
- lightly show counts when present

Explicitly not in scope:

- new page
- new progress console
- layout redesign
- `M2D-15D` visual upgrade

## Acceptance Criteria

`M2D-15A` is complete only if:

1. long-running real PDF jobs no longer appear as only `queued/running` for most of the lifecycle
2. API polling returns meaningful `current_step` and `progress_message`
3. PDF parser OCR / layout / table / merge phases are visible
4. embedding batch sub-progress is visible
5. completed jobs expose `chunk_count = embedding_count = vector_mapping_count`
6. failed jobs expose the actual failing stage
7. no worker queue, SSE/WebSocket, retrieval/rerank/answer, or `M2D-15D` redesign work is introduced

