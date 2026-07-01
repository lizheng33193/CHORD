# M2D-14C-3 Real PDF Validation Review

## Scope

This review closes the third targeted validation step inside `M2D-14C Targeted File-Type Validation`.

This closure is intentionally narrow:

- record one successful local `real PDF` smoke
- confirm the accepted admin/runtime surfaces can parse, index, activate, and retrieve a real local `PDF`
- record the runtime prerequisites observed during the real `PDF` path
- record the timing and observability characteristics exposed by the real `PDF` path
- keep `M2D-15 Production Hardening` not started

This review does not change runtime behavior, API behavior, UI behavior, retrieval/rerank/answer logic, worker-queue posture, streaming posture, or production-hardening scope.

## Exact Real PDF Validation Flow

Local smoke used one real local `PDF` input and executed the following flow:

1. verify clean branch state and local runtime prerequisites
2. inspect the real `PDF` at `/Users/zhengli/Desktop/workspace/CHORD-local-test-docs/智能风控实践指南.pdf`
3. record file size and page count
4. prepare `/tmp/chord_m2d_real_pdf_validation.pdf`
5. clear `kb_id=risk_domain_knowledge` durable state from MySQL
6. clear risk-knowledge upload/output local artifacts
7. clear risk-knowledge Redis prefix state
8. restart `scripts.local_mysql.local_stack`
9. verify `GET /health`
10. call admin login
11. call `POST /api/risk-knowledge/admin/kbs`
12. call `POST /api/risk-knowledge/admin/kbs/{kb_id}/documents`
13. call `POST /api/risk-knowledge/admin/documents/{document_id}/versions:upload`
14. call `POST /api/risk-knowledge/admin/versions/{version_id}:index`
15. poll `GET /api/risk-knowledge/admin/indexing-jobs/{job_id}` until terminal state
16. call `POST /api/risk-knowledge/admin/versions/{version_id}:activate`
17. call `POST /api/risk-knowledge/admin/debug/retrieve` for five targeted risk queries

## Runtime Prerequisites

The following local prerequisites were present or observed during the successful real `PDF` path:

- `java -version` remained unavailable locally
- `libomp` path existed:
  - `/opt/homebrew/opt/libomp/lib`
- `xgboost` import succeeded
- `huggingface_hub` import succeeded
- NLTK runtime data was present:
  - `punkt`
  - `punkt_tab`
  - `wordnet`
  - `omw-1.4`
  - `stopwords`
- `SwxyParserAdapter()._load_default_chunker()` loaded successfully
- valid local `DASHSCOPE_API_KEY` was present
- `.env.local-mysql` provided:
  - `SSL_CERT_FILE`
  - `REQUESTS_CA_BUNDLE`
  - `CURL_CA_BUNDLE`
  - `DYLD_LIBRARY_PATH`
  - `DYLD_FALLBACK_LIBRARY_PATH`
- CA bundle files existed locally
- dynamic-library paths existed locally

These are local validation prerequisites, not a production-hardening claim.

## Cleanup Summary

The smoke started from a targeted cleanup of `kb_id=risk_domain_knowledge` only.

Cleanup counts before:

- `knowledge_bases=1`
- `knowledge_documents=1`
- `knowledge_document_versions=1`
- `knowledge_ingest_jobs=1`
- `knowledge_chunks=13`
- `knowledge_chunk_embeddings=13`
- `faiss_index_manifests=1`
- `faiss_vector_mappings=13`

Cleanup counts after:

- `knowledge_bases=0`
- `knowledge_documents=0`
- `knowledge_document_versions=0`
- `knowledge_ingest_jobs=0`
- `knowledge_chunks=0`
- `knowledge_chunk_embeddings=0`
- `faiss_index_manifests=0`
- `faiss_vector_mappings=0`

Additional targeted cleanup completed:

- `storage/risk_knowledge/uploads/*`
- `outputs/risk_knowledge/*`
- Redis prefix delete count: `2` keys under `chord:risk_knowledge*`

No database drop, volume deletion, or Redis-wide flush was performed.

## Indexing Result Evidence

The real `PDF` smoke completed successfully with the following artifacts:

- real `PDF` path: `/Users/zhengli/Desktop/workspace/CHORD-local-test-docs/智能风控实践指南.pdf`
- upload temp path: `/tmp/chord_m2d_real_pdf_validation.pdf`
- file size: `26,482,250` bytes
- page count: `253`
- branch HEAD before closure: `6b976b55f5d13de73e2441b99ae6c0d98ec1650d`
- KB create: success, `kb_id=risk_domain_knowledge`
- Document create: success, `document_id=item`
- Version upload: success, `version_id=item_real_pdf_v1`
- job id: `idxjob_a7bbd18187a7489caccd8a5117977e31`
- index job status: `completed`
- `error_message=null`
- manifest id: `idx_item_real_pdf_v1_8a5117977e31`
- activate result: `already_active`

Final durable state also showed:

- KB status: `active`
- document status: `active`
- version status: `active`
- `latest_manifest_index_id=idx_item_real_pdf_v1_8a5117977e31`
- `active_manifest_index_id=idx_item_real_pdf_v1_8a5117977e31`

This confirms that the current local runtime can complete:

- parse
- chunk
- embed
- index
- activate
- retrieve

for a real local `PDF` without expanding product scope.

## Timing Evidence

Observed timing for the successful real `PDF` path:

- durable wall-clock duration: about `10m12s`
- runtime-state phase duration: about `81.22s`

Observed parser/runtime timing evidence from logs:

- `OCR(0~100000): 252.17s`
- `layouts cost: 520.1496500829817s`
- `naive_merge(...): 6.894869875046425`
- FAISS load occurred immediately before final completion

The real `PDF` path was materially slower than the small `PDF` path and exposed longer parser-side work before runtime-state visibility became available.

## Chunk, Embedding, and FAISS Counts

Completed real `PDF` indexing persisted the following counts:

- `knowledge_chunks=1139`
- `knowledge_chunk_embeddings=1139`
- `faiss_index_manifests=1`
- `faiss_vector_mappings=1139`

The active manifest also reported:

- `build_status=active`
- `record_count=1139`

This confirms that chunk persistence, embedding persistence, FAISS manifest persistence, and vector mapping persistence all completed for the real `PDF` version.

## Retrieval Evidence Summary

`debug/retrieve` completed successfully for five targeted queries, each with `top_k=5`.

Observed retrieval evidence:

1. query `什么是多头借贷风险？`
   - candidate count: `5`
   - top preview mentioned `近7天多头借贷`
2. query `贷前风控主要关注哪些风险信号？`
   - candidate count: `5`
   - top preview mentioned `身份验证、反欺诈、信用评估、额度和定价评估`
3. query `短期高频申请代表什么风险？`
   - candidate count: `5`
   - top preview mentioned `短期内频繁出现提前还款后立即再次借款` and `疑似撸贷风险`
4. query `风控策略如何识别欺诈风险？`
   - candidate count: `5`
   - top preview mentioned `身份验证、活体识别、第三方数据验证及反欺诈模型`
5. query `逾期风险如何评估？`
   - candidate count: `5`
   - top preview mentioned `样本逾期率、整体逾期率、lift 等规则效果指标`

This confirms that retrieval candidates were produced from the indexed real `PDF` content and reflected expected risk-domain semantics after activation.

## Observations

The real `PDF` validation exposed an observability issue during long parser-side execution.

Observed behavior:

- external job summary stayed at `running / queued` for a long time
- `runtime_state_available=false` remained visible for much of the parser-side work
- logs simultaneously showed OCR, layout processing, merge activity, FAISS load, and eventual completion

This should be tracked as an observability / production-hardening candidate only.

This review does not escalate that observation into:

- runtime changes
- API changes
- UI changes
- retrieval changes
- worker-queue changes
- `M2D-15 Production Hardening` start

Java also remained unavailable locally during this validation, but it was not a blocker for the successful real `PDF` path.

## Remaining Production Gaps

Still not covered by this validation closure:

- no production worker queue
- no SSE / WebSocket
- no production-hardening observability work
- no parser-progress API improvements
- no retry/resume hardening for long-running indexing jobs
- no large-scale concurrent workload validation
- no production deployment hardening
- `M2D-15 Production Hardening` not started

`debug/retrieve` remains retrieval-only v1 and this review does not expand into answer/evidence/rerank acceptance.

## Acceptance Conclusion

`M2D-14C-3 real PDF validation passed`.

This is a local targeted validation milestone inside `M2D-14C`, not a production-readiness milestone and not the start of `M2D-15`.
