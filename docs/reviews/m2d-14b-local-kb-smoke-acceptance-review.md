# M2D-14B Local KB Smoke Acceptance Review

## Scope

This review closes the local acceptance loop for `M2D-14B` after the stage-level UI Console delivery was already accepted.

This closure is intentionally narrow:

- record the verified local `md` knowledge-base smoke
- record the UI-side verification result
- record the local-only runtime prerequisites and blockers that were resolved during smoke
- keep `M2D-15 Production Hardening` not started

This review does not change runtime behavior, frontend behavior, parser implementation, API contracts, or deployment posture.

## What Was Verified

Verified facts in local development:

- the `knowledge` UI Console page is reachable and usable
- a local `md` file can complete the full KB admin chain:
  - create KB
  - create Document
  - upload Version
  - index
  - activate
  - `debug/retrieve`
- the indexing job completed successfully
- the activated manifest id is `idx_item_v1_1f264b276372`
- `debug/retrieve` returned `1` candidate for query `什么是多头借贷风险？`
- the returned candidate matched the uploaded document chunk
- the local dirty-state cleanup was completed afterward:
  - `.env.example` restored
  - stray SWXY runtime cache file removed
  - `git status` returned clean

## Exact Smoke Flow

Local smoke used a minimal markdown file and executed the following flow against the accepted `M2D-14A/M2D-14B` surfaces:

1. verify local prerequisites required by the parser and embedding path
2. clear `kb_id=risk_domain_knowledge` durable state from MySQL
3. clear risk-knowledge upload/output local artifacts
4. clear risk-knowledge Redis prefix state
5. restart `scripts.local_mysql.local_stack`
6. call admin login
7. call `POST /api/risk-knowledge/admin/kbs`
8. call `POST /api/risk-knowledge/admin/kbs/{kb_id}/documents`
9. call `POST /api/risk-knowledge/admin/documents/{document_id}/versions:upload`
10. call `POST /api/risk-knowledge/admin/versions/{version_id}:index`
11. poll `GET /api/risk-knowledge/admin/indexing-jobs/{job_id}` until terminal state
12. call `POST /api/risk-knowledge/admin/versions/{version_id}:activate`
13. call `POST /api/risk-knowledge/admin/debug/retrieve`

Verified local successful result:

- `job status=completed`
- `manifest id=idx_item_v1_1f264b276372`
- `activate result=already_active`
- `retrieval candidate_count=1`

## UI Verification Result

The dashboard-side `Knowledge Base UI Console` was also verified against the same local environment.

Confirmed from the page:

- KB list and detail surfaces are usable
- document and version management surfaces are usable
- the uploaded local markdown document can be indexed and activated
- `query=什么是多头借贷风险？` returns the uploaded document chunk in the retrieval debug panel

This closes the local UI + API smoke loop for the minimal markdown path.

## Local Runtime Blockers Fixed

The following local-only blockers were resolved during smoke bring-up and are now part of the recorded local acceptance context:

- parser dependency bootstrap already landed in commit `6f20496`
- `local_stack` runtime bootstrap via `sys.executable` already landed in commit `969b343`
- CA bundle env wiring is required in `.env.local-mysql`:
  - `SSL_CERT_FILE`
  - `REQUESTS_CA_BUNDLE`
  - `CURL_CA_BUNDLE`
- the CA bundle paths point to local `certifi` `cacert.pem`
- NLTK runtime data required by the parser/tokenizer path is present:
  - `punkt`
  - `punkt_tab`
  - `wordnet`
  - `omw-1.4`
  - `stopwords`
- parser-side local dependencies are available, including `python-docx` and `tika`
- real embedding smoke requires a valid local `DASHSCOPE_API_KEY`

These are local smoke prerequisites, not a production-hardening claim.

## Known Remaining Gaps

Still not covered by this acceptance closure:

- PDF validation
- DOCX validation
- large-document validation
- long-running or concurrent indexing validation
- production worker queue validation
- SSE / WebSocket job streaming
- production deployment hardening
- full repository regression for this closure

`debug/retrieve` remains retrieval-only v1 and this review does not expand it into answer/evidence/rerank debug acceptance.

## Not Started Boundaries

The following boundaries remain explicit after this closure:

- `M2D-15 Production Hardening` not started
- no production worker queue
- no SSE / WebSocket
- no Data Agent RAG mixing
- no ES / SWXY runtime coupling expansion
- no standalone admin app
- no production observability expansion
- no parser rework
- no frontend behavior expansion beyond the accepted UI Console

## Acceptance Closure

`M2D-14B` can now be described more precisely as:

- stage-level UI Console acceptance passed
- local markdown KB smoke passed end-to-end

This is still a local acceptance milestone, not a production-readiness milestone.
