# M2D-14A Knowledge Base Admin API Spec

## Baseline

`M2D-14A` starts from the accepted `M2D-13` baseline:

- source branch: `origin/codex/m2d-13-golden-evaluation`
- acceptance closure commit: `fd26319`

The earlier local `M2D-10` reading was a stale worktree issue, not a missing `M2D-11~13` implementation gap.

## Scope

`M2D-14A` delivers a management-only backend surface for the risk knowledge base:

- durable knowledge-base CRUD
- document registration
- local file upload
- version indexing / rebuild / retry / status
- manifest activation
- retrieval-only debug API

This phase does not start:

- UI console or frontend changes
- worker queue or production async runtime
- Data Agent RAG coupling
- answer/evidence debug APIs

## API Surface

Route prefix: `/api/risk-knowledge/admin`

Endpoints:

- `POST /kbs`
- `GET /kbs`
- `GET /kbs/{kb_id}`
- `POST /kbs/{kb_id}/documents`
- `GET /kbs/{kb_id}/documents`
- `GET /documents/{document_id}`
- `POST /documents/{document_id}/versions:upload`
- `GET /documents/{document_id}/versions`
- `GET /versions/{version_id}`
- `POST /versions/{version_id}:index`
- `POST /versions/{version_id}:rebuild`
- `POST /versions/{version_id}:activate`
- `GET /indexing-jobs/{job_id}`
- `GET /indexing-jobs`
- `POST /indexing-jobs/{job_id}:retry`
- `POST /debug/retrieve`

Success responses use `response_model`. Failures use HTTP status plus `detail.code` and `detail.message`.

## Implementation Notes

- `app/knowledge_base` now persists durable `KnowledgeBase` state in SQLAlchemy without adding a migration framework.
- `app/risk_knowledge/admin/` owns admin DTOs, error mapping, upload handling, indexing/job management, and retrieval-debug shaping.
- uploads remain local-only under `RISK_KNOWLEDGE_UPLOAD_DIR`
- uploads use stream write, SHA-256 during write, temp file, and atomic rename
- document metadata is updated to the uploaded file type/path before version creation
- `:index` and `:rebuild` are job-based APIs that return immediately with job metadata
- current runtime remains in-process; production async worker queue stays in `M2D-15`
- Redis is supplemental for progress/heartbeat only; MySQL durable job state remains the fact source

## Debug Retrieve v1 Boundary

`POST /debug/retrieve` is intentionally retrieval-only in `M2D-14A`.

Request fields:

- `kb_id`
- `query`
- `document_id?`
- `version_id?`
- `top_k?` with default `10` and max `50`

Response fields:

- `query`
- `kb_id`
- `scope`
- `candidates`
- `diagnostics`

Explicitly excluded:

- `rerank_items`
- `selected_evidence`
- `citations`
- `gate_decision`
- `answer`

Future evidence or answer debugging belongs in a later surface such as `debug/evidence`.
