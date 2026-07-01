# M2D-14C-2 Small PDF Validation Review

## Scope

This review closes the second targeted validation step inside `M2D-14C Targeted File-Type Validation`.

This closure is intentionally narrow:

- record one successful local `small PDF` smoke
- record the dependency unblock and validation-driven runtime fix required to make the `PDF` path pass
- confirm the accepted admin/runtime surfaces can parse, index, activate, and retrieve a local `small PDF`
- keep `M2D-15 Production Hardening` not started

This review does not change public APIs, UI behavior, retrieval/rerank/answer logic, worker-queue posture, or streaming posture.

## Exact Small PDF Smoke Flow

Local smoke used one local `small PDF` input and executed the following flow:

1. verify local prerequisites required by parser and embedding runtime
2. prepare `/tmp/chord_m2d_smoke_pdf_v1.pdf`
3. clear `kb_id=risk_domain_knowledge` durable state from MySQL
4. clear risk-knowledge upload/output local artifacts
5. clear risk-knowledge Redis prefix state
6. restart `scripts.local_mysql.local_stack`
7. verify `GET /health`
8. call admin login
9. call `POST /api/risk-knowledge/admin/kbs`
10. call `POST /api/risk-knowledge/admin/kbs/{kb_id}/documents`
11. call `POST /api/risk-knowledge/admin/documents/{document_id}/versions:upload`
12. call `POST /api/risk-knowledge/admin/versions/{version_id}:index`
13. poll `GET /api/risk-knowledge/admin/indexing-jobs/{job_id}` until terminal state
14. if completed, call `POST /api/risk-knowledge/admin/versions/{version_id}:activate`
15. if activation succeeds, call `POST /api/risk-knowledge/admin/debug/retrieve`

## First Failure: libomp / xgboost Missing

The first small `PDF` attempt failed before retrieval and before any production-hardening concern.

First blocking error:

- `SWXY parser execution failed: xgboost runtime is unavailable for SWXY PDF parsing`
- concrete loader failure:
  - `Library not loaded: @rpath/libomp.dylib`

This established that the initial `small PDF` blocker was not:

- Java first
- FAISS first
- retrieval first
- rerank first

It was a local parser-runtime dependency issue on the `PDF` path.

## Dependency Unblock Result

The local dependency blocker was resolved without changing product scope:

- `libomp` path present:
  - `/opt/homebrew/opt/libomp/lib/libomp.dylib`
- `.env.local-mysql` carried:
  - `DYLD_LIBRARY_PATH=/opt/homebrew/opt/libomp/lib`
  - `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/opt/libomp/lib`
- both dynamic-library paths existed locally
- `xgboost` import succeeded after the local runtime dependency became available

This moved the `small PDF` path past parser-runtime loading and allowed a second validation attempt.

## Second Failure: DashScope Batch Size Limit

After the parser-runtime dependency unblock, rerun progressed further and exposed a new runtime blocker in the embedding stage:

- `dashscope embedding request failed`
- `InvalidParameter`
- `batch size is invalid, it should not be larger than 10`

This showed the remaining blocker was request shaping for the embedding provider, not the `PDF` parser path itself.

## Validation-Driven Runtime Fix Summary

The validation-driven runtime fix was delivered in commit `407f058`:

- commit: `407f058`
- message: `fix: batch dashscope embeddings for m2d pdf validation`

Changed files:

- `app/risk_knowledge/embedding/base.py`
- `app/risk_knowledge/embedding/batch_service.py`
- `app/risk_knowledge/embedding/dashscope_provider.py`
- `tests/risk_knowledge/embedding/test_embedding_runtime.py`

Behavioral change:

- `DashScopeEmbeddingProvider` now declares `max_batch_size = 10`
- `EmbeddingBatchService.embed_inputs()` now batches provider calls by `provider.max_batch_size`
- `EmbeddingBatchService.embed_persisted_chunks()` now uses the same batching path
- dimension validation, idempotent persistence, and commit semantics remain unchanged

This was a validation-driven runtime fix inside `M2D-14C`, not an `M2D-15 Production Hardening` start.

## Tests Run

The embedding-layer fix was verified with targeted unit tests:

- `pytest tests/risk_knowledge/embedding/test_embedding_runtime.py -q`
- `pytest tests/risk_knowledge/embedding -q`

Observed result:

- `13 passed, 3 skipped`

## Final Successful PDF Smoke Evidence

After the dependency unblock and embedding batching fix, the `small PDF` smoke completed successfully:

- KB create: success, `kb_id=risk_domain_knowledge`
- Document create: success, `document_id=pdf`
- Version upload: success, `version_id=pdf_pdf_v1`
- index job status: `completed`
- `error_message=null`
- manifest id: `idx_pdf_pdf_v1_de287f5337dd`
- activate result: `already_active`
- retrieval candidate count: `5`

Observed successful job timing:

- polling reached terminal completion in about `16.41s`

## Retrieval Evidence Summary

`debug/retrieve` completed successfully for query `Multiple lending risk`.

The returned candidates included text that matched the uploaded `PDF` content and the expected risk-domain semantics, including:

- `Multiple lending means a user frequently applies for or uses credit products on multiple platforms`
- `Main Reason: Multiple Lending Risk`
- `CHORD Risk Knowledge PDF Smoke Test`

This confirms that the current local runtime can complete:

- parse
- chunk
- embed
- index
- activate
- retrieve

for a local `small PDF` after the validation-driven embedding batching fix.

## Local Prerequisites Now Required

The local prerequisites validated or required by the successful `small PDF` path are:

- `libomp`
- `DYLD_LIBRARY_PATH` in `.env.local-mysql`
- `DYLD_FALLBACK_LIBRARY_PATH` in `.env.local-mysql`
- valid local `DASHSCOPE_API_KEY`
- `SSL_CERT_FILE`
- `REQUESTS_CA_BUNDLE`
- `CURL_CA_BUNDLE`
- local `certifi` CA bundle paths
- NLTK runtime data:
  - `punkt`
  - `punkt_tab`
  - `wordnet`
  - `omw-1.4`
  - `stopwords`

These are local runtime prerequisites for validation, not a production-hardening claim.

## Observation

Java remained unavailable locally during this validation.

Observed result:

- `java -version` unavailable

However, Java was not the first blocker for this `small PDF` validation path.

The observed first blockers were:

1. `libomp / xgboost`
2. DashScope embedding batch-size limit

## Remaining Gaps

Still not covered by this validation closure:

- real large PDF not validated
- large document latency not validated
- production worker queue not started
- SSE / WebSocket not started
- `M2D-15 Production Hardening` not started

`debug/retrieve` remains retrieval-only v1 and this review does not expand into answer/evidence/rerank acceptance.

## Acceptance Conclusion

`M2D-14C-2 small PDF validation passed after validation-driven embedding batching fix`.

This is still a local targeted validation milestone inside `M2D-14C`, not a production-readiness milestone and not the start of `M2D-15`.
