# M2D Existing RAG Integration Review

## 1. Review Purpose

This review evaluates SWXY as an implementation asset source for `M2D`.

Current `M2D` status remains:

> `planned; contract/review/design in progress`

This review does not migrate SWXY code and does not start runtime implementation.

## 2. SWXY RAG Main Chain

The SWXY RAG main chain is:

`upload_files -> parse/chunk -> embedding -> ES hybrid index -> retrieval -> rerank`

This chain is useful as an engineering reference because it already covers the major ingestion and retrieval steps needed by `M2D`.

## 3. Direct Reuse Assets

The following SWXY assets are valid direct-reuse candidates at the engineering-asset level:

- `backend/app/service/core/deepdoc`
- `backend/app/service/core/rag/app/naive.py`
- `backend/app/service/core/rag/nlp`
- `backend/app/service/core/rag/utils/doc_store_conn.py`
- `backend/app/service/core/rag/utils/es_conn.py`
- `backend/app/service/core/file_parse.py`
- `backend/app/service/core/retrieval.py`
- `backend/app/service/core/conf/mapping.json`
- `backend/app/service/core/api/utils/file_utils.py`
- `backend/app/service/core/rag/res`

These assets are relevant because they contain reusable parsing, chunking, retrieval, ES, and model-resource building blocks.

## 4. Adapter Required Assets

The following SWXY assets require CHORD-specific adapters or rewrites before any later migration:

- `backend/app/router/chat_rt.py`
  - only reuse the upload-flow idea
  - do not migrate old route structure, auth, or DB coupling
- `backend/app/service/core/retrieval.py`
  - must replace `user_id/indexNames` semantics with explicit `kb_id/index_name`
- `backend/app/service/core/file_parse.py`
  - must replace `session_id/user_id/index_name` semantics with `kb_id/doc_id/version_id/index_name`
- `backend/app/service/document_operations.py`
  - delete and deprecate flow must be rewritten for CHORD document lifecycle
- `backend/app/database/knowledgebase_operations.py`
  - record-layer ownership must be rewritten for CHORD contracts
- `backend/app/service/core/chat.py`
  - only keep the idea of feeding retrieval results into the LLM
  - do not migrate old session naming, recommended questions, or Redis temporary-document logic

## 5. Do Not Migrate Assets

The following SWXY assets are explicitly out of scope for migration:

- `frontend`
- `user/history/auth routes`
- `backend/app/models`
- `backend/init.sql`
- `quick_parse_service.py`
- old chat prompt/session/history/Redis logic

These assets belong to the old application shell and would import business coupling that `M2D` must avoid.

## 6. Dependency Requirements

SWXY indicates the likely dependency surface for future `M2D` implementation work:

- `openai`
- `dashscope`
- `llama-index-core`
- `llama-index-postprocessor-dashscope-rerank-custom`
- `elasticsearch`
- `elasticsearch-dsl`
- `onnxruntime`
- `opencv-python`
- `shapely`
- `pyclipper`
- `xgboost`
- `pdfplumber`
- `pypdf`
- `python-docx`
- `openpyxl`
- `python-pptx`
- `tika`
- `datrie`
- `hanziconv`
- `nltk`
- `jieba`
- `tiktoken`
- `chardet`
- `huggingface_hub`

This review records them only as future implementation context. No dependency is added in this pass.

## 7. Environment Variables

Relevant SWXY-style environment variables include:

- `DASHSCOPE_API_KEY`
- `DASHSCOPE_BASE_URL`
- `ES_HOST`
- `HF_ENDPOINT`
- `RAG_PROJECT_BASE`
- `RAG_DEPLOY_BASE`

Redis, PostgreSQL, and JWT-related configuration are not default `M2D v1` requirements unless CHORD intentionally keeps old temporary-parse, record-layer, or auth coupling from SWXY, which this review explicitly rejects.

## 8. Critical Coupling Risks

The most important migration risks are:

- `user_id/session_id -> index_name`
  - this strong coupling must be removed and replaced with explicit `kb_id/doc_id/version_id/index_name`
- `quick_parse` is not long-term KB
  - the temporary single-session parse branch is not the `M2D` knowledge-base mainline
- old chat prompt/session logic must not migrate
  - legacy conversation shell logic would pollute CHORD runtime boundaries
- `mapping.json` and field names must stay aligned
  - ES mappings and runtime field names must remain contract-aligned during future migration
- `rag/res` and `deepdoc` resources are mandatory
  - model resources are not optional packaging details; they are part of the actual engine capability

## 9. ES Hybrid Retrieval Decision

`M2D v1` should keep Elasticsearch hybrid retrieval as the default direction because it supports:

- fulltext retrieval
- keyword filter
- dense-vector retrieval
- metadata filter
- rerank integration

This review records ES as the preferred v1 retrieval backend direction only. It does not implement any ES runtime.

## 10. Migration Decision

Final decision:

> Do not migrate SWXY as an application. Migrate it as a third-party RAG engine asset.

SWXY can be reused as a third-party RAG engine asset, but CHORD must wrap it through `M2D` adapters and contracts rather than importing the old business subsystem shape.
