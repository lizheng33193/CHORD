# M2D-6 SWXY Ingestion Adapter Review

## Summary

This phase introduces a CHORD-owned ingestion adapter boundary that normalizes SWXY-compatible parser/chunker output into `ParsedDocument / RawParsedChunk` contracts and advances knowledge-base version/job lifecycle state.

It does not materialize `KnowledgeChunk`, compute hashes, embed content, write Elasticsearch, retrieve, rerank, build evidence, expose APIs, or integrate with Agents.

Current top-level project reading for `M2D` is:

> `M2D implementation in progress`

Current subphase reading is:

> `M2D-6 SWXY ingestion adapter landed; no embedding/retrieval/ES runtime started`

## Scope

This phase is intentionally limited to:

- ingestion input context
- normalized parser-side contracts
- SWXY-compatible parser/chunker adapter
- parser lifecycle coordination with `document_version` and `ingest_job`
- fake-parser-driven tests

This phase does not start embedding, indexing, retrieval, evidence shaping, APIs, or consumer integration.

## Added Runtime Boundary

This phase adds:

- `app/risk_knowledge/`
- `app/risk_knowledge/ingestion/`

The subtree contains:

- `IngestionContext`
- `SourceDocumentRef`
- `RawParsedChunk`
- `ParsedDocument`
- ingestion errors
- `SwxyParserAdapter`
- `SwxyIngestionPipeline`

## Adapter Contract

The adapter input contract is:

- `kb_id`
- `doc_id`
- `version_id`
- `job_id`
- `file_path`
- `doc_name`
- `source_type`

The adapter output contract is:

- `ParsedDocument`
- `RawParsedChunk`

`ParsedDocument` remains parser-side output only. It is not retrieval-ready output and does not hold `KnowledgeDocumentVersion` objects directly.

## SWXY Boundary

The default parser/chunker target is the vendored SWXY `rag.app.naive.chunk` entry, wrapped behind `SwxyParserAdapter`.

Boundary rules in this phase are:

- SWXY is loaded only through lazy import inside the adapter
- `app.third_party.swxy_rag` is not imported by schemas, context, pipeline, or tests
- `file_parse_core.py` is not used
- `retrieval_core.py` is not used
- ES/embedding/retrieval helpers are not used

The adapter normalizes SWXY-compatible chunk dicts into CHORD-owned `RawParsedChunk` structures.

## Knowledge Base Interaction

The pipeline only advances:

- `document_version: uploaded -> parsing -> parsed -> failed`
- `ingest_job: uploaded -> parsing -> parsed -> failed`

The only required `app/knowledge_base` extension in this phase is:

- `DocumentService.transition_version(version_id, next_status)`

This method remains a narrow lifecycle helper and does not introduce chunk persistence, ES behavior, or retrieval behavior.

## Dependency Policy

M2D-6 does not activate SWXY OCR/ONNX/ES/DashScope dependencies.

All required tests use dependency-injected fake parser outputs.

The default SWXY loader is lazy and is not exercised by required tests.

Real-file parsing smoke is deferred until parser dependencies are enabled.

## Explicitly Not Started

The following remain intentionally not started:

- `KnowledgeChunk` persistence
- content hashing
- embedding
- ES indexing
- retrieval
- rerank
- Evidence Builder
- `RiskKnowledgeService`
- upload/reindex/status API
- NL Chat integration
- Profile Explanation integration

## Validation

The following validation commands were run:

- `pytest -q tests/risk_knowledge/ingestion tests/knowledge_base`
  - result: `69 passed`
- `python - <<'PY' ... importlib.util.find_spec(...) ... PY`
  - result: representative `app.risk_knowledge` and ingestion modules were discoverable
- `python - <<'PY' ... ast.parse(...) ... PY`
  - result: syntax check passed for `app/risk_knowledge` and `tests/risk_knowledge`
- precise coupling guard search over `app/risk_knowledge` and `tests/risk_knowledge`
  - result: forbidden SWXY/ES/DashScope/RiskKnowledgeService imports were not introduced outside the adapter lazy loader boundary

## Status

`M2D implementation in progress`

`M2D-6 SWXY ingestion adapter landed; no embedding/retrieval/ES runtime started`

## Next Step

`M2D-7 Metadata & Evidence Builder`
