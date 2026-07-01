# M2D-14C-1 Small DOCX Validation Review

## Scope

This review records the first execution closure inside `M2D-14C Targeted File-Type Validation`.

This closure is intentionally narrow:

- record one successful local `small DOCX` smoke
- confirm the accepted `M2D-14A/M2D-14B` runtime can parse, index, activate, and retrieve a local `DOCX`
- keep runtime, API, UI, retrieval, rerank, and answer behavior unchanged
- keep `M2D-15 Production Hardening` not started

This review does not change runtime behavior, parser implementation, API contracts, UI behavior, or deployment posture.

## Exact DOCX Smoke Flow

Local smoke executed the following flow against the accepted admin/runtime surfaces:

1. verify local prerequisites required by the parser and embedding path
2. create `/tmp/chord_m2d_smoke_docx_v1.docx`
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
14. call `POST /api/risk-knowledge/admin/versions/{version_id}:activate`
15. call `POST /api/risk-knowledge/admin/debug/retrieve`

## Cleanup Summary

The smoke started from a targeted cleanup of `kb_id=risk_domain_knowledge` only.

Cleanup counts before:

- `knowledge_bases=1`
- `knowledge_documents=1`
- `knowledge_document_versions=1`
- `knowledge_ingest_jobs=1`
- `knowledge_chunks=1`
- `knowledge_chunk_embeddings=1`
- `faiss_index_manifests=1`
- `faiss_vector_mappings=1`

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

## Runtime Prerequisites Used

The following local prerequisites were present during smoke execution:

- valid local `DASHSCOPE_API_KEY`
- `.env.local-mysql` provided:
  - `SSL_CERT_FILE`
  - `REQUESTS_CA_BUNDLE`
  - `CURL_CA_BUNDLE`
- CA bundle paths resolved to local `certifi` `cacert.pem`
- NLTK runtime data was present:
  - `punkt`
  - `punkt_tab`
  - `wordnet`
  - `omw-1.4`
  - `stopwords`
- parser-side dependencies imported successfully:
  - `python-docx`
  - `tika`
- `SwxyParserAdapter()._load_default_chunker()` loaded successfully
- local stack restarted successfully and `GET /health` returned `{"status":"ok"}`

These are local validation prerequisites, not a production-hardening claim.

## Result Evidence

Verified local successful result:

- DOCX file: `/tmp/chord_m2d_smoke_docx_v1.docx`
- KB create: success, `kb_id=risk_domain_knowledge`
- Document create: success, `document_id=docx`
- Version upload: success, `version_id=docx_docx_v1`
- Index job: `completed`
- `error_message=null`
- manifest id: `idx_docx_docx_v1_56051cb271ee`
- activate result: `already_active`
- retrieval candidate count: `1`

Observed index timing:

- polling reached terminal state in about `4.2s`

## Retrieval Preview Summary

`debug/retrieve` returned one candidate for query `什么是多头借贷风险？`.

The returned preview matched the uploaded `DOCX` content, including:

- `风控知识库 DOCX 测试文档`
- `多头借贷风险`
- `短期高频申请`

This confirms the current local runtime can parse, chunk, index, activate, and retrieve the test `DOCX` without runtime expansion.

## Observation

During smoke execution, the `create document` response returned `source_type=unknown`.

This did not block:

- upload
- index
- activate
- retrieval

The behavior should be tracked as an observation only for this closure and is not being escalated into a runtime/API change inside `M2D-14C-1`.

## Known Remaining Gaps

Still not covered by this validation closure:

- small PDF not validated
- real large PDF not validated
- Java/Tika PDF runtime not validated
- libomp/PDF parser path not validated
- `M2D-15 Production Hardening` not started

`debug/retrieve` remains retrieval-only v1 and this review does not expand into answer/evidence/rerank acceptance.

## Acceptance Conclusion

`M2D-14C-1 small DOCX validation passed`.

This is a local targeted validation milestone inside `M2D-14C`, not a production-readiness milestone and not a start of `M2D-15`.
