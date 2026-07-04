# Risk QA Production Gate Contract

## Status

Current phase:

> `PR-A Risk QA + Context Isolation + Evidence/Citation Production Gate`

This contract upgrades the existing `risk_knowledge_answer` path into a production-gated Risk QA flow without changing its public entrypoints.

## 1. Public Compatibility

PR-A keeps the following public surfaces stable:

- orchestrator intent: `risk_knowledge_answer`
- public facade: `RiskKnowledgeService.answer()`
- existing orchestrator flow: `RiskKnowledgeAnswerFlow`

PR-A does not introduce a second public Risk QA route and does not perform a repo-wide rename to `risk_qa_*`.

## 2. Facade Boundary

`RiskKnowledgeService` is a compatibility facade only.

Its responsibilities are limited to:

- translating `RiskKnowledgeQuery` into the internal Risk QA request
- calling the internal QA pipeline
- mapping the internal result back to the extended `RiskKnowledgeAnswer`
- preserving the legacy answer text contract
- exposing additive artifact metadata

`RiskKnowledgeService` must not directly own:

- evidence selection
- sufficiency evaluation
- answer generation
- citation validation
- context isolation policy

## 3. Internal Pipeline

PR-A introduces an internal pipeline with the following sequence:

`query -> context isolation -> retrieval normalization -> evidence selection -> sufficiency check -> answer generation -> citation validation -> artifact shaping`

The internal modules live under:

- `app/risk_knowledge/qa/`
- `app/risk_knowledge/context/`
- `app/risk_knowledge/evidence/manager.py`

These modules are implementation details and must not replace the current public facade names.

## 4. Source Isolation Policy

For `risk_knowledge_answer`, the context policy is:

- allow: `risk_domain_knowledge`
- block: `data_knowledge`
- block: `sql_examples`
- block: `sql_error_cases`
- block: `catalog_grounding`
- block: `memory_as_authority`

Blocked sources must be recorded in the returned artifact.

Risk QA may use only `risk_domain_knowledge` as authoritative answer evidence.

Data-side routes must remain unable to use Risk Domain Knowledge as field grounding.

## 5. Evidence Contract

PR-A normalizes retrieval candidates into a richer evidence contract.

Each normalized evidence item must preserve when available:

- `evidence_id`
- `source_type`
- `document_id`
- `document_name`
- `document_version`
- `section_title`
- `section_path`
- `page_start`
- `page_end`
- `chunk_id`
- `evidence_text`
- `score`
- `used_in_answer`
- `citation_label`
- `warnings`

PR-A may normalize future-compatible source types for trace purposes, but answer citations are restricted to:

- `source_type = risk_domain_knowledge`

## 6. Sufficiency Contract

The pipeline must emit one of:

- `grounded`
- `partial`
- `insufficient_evidence`

`insufficient_evidence` is a pre-generation hard stop.

If evidence is missing, below threshold, empty, or lacks required provenance, the pipeline must:

- skip answer generation
- return a safe refusal artifact
- mark `grounding_status=insufficient_evidence`

## 7. Citation Gate

Citation validation is a public-answer gate.

Grounded answers must satisfy all of the following:

- every citation points to selected evidence
- every citation source type is `risk_domain_knowledge`
- every citation includes `chunk_id`
- key grounded conclusions are cited

The following must block grounded output:

- citations to non-selected evidence
- citations to `data_knowledge`
- citations to SQL examples
- citations to SQL error cases
- citations to catalog-grounding artifacts
- citations to memory
- uncited grounded conclusions

If citation validation fails, the system may attempt at most one repair/regeneration pass.
If validation still fails, the result must degrade to `partial` or `insufficient_evidence`.
It must never return an unvalidated grounded answer.

## 8. Public Answer Contract

PR-A extends the existing public answer contract additively with:

- `schema_version`
- `grounding_status`
- `citations`
- `evidence_trace`
- `retrieval_snapshot_id`
- `blocked_context_sources`
- `context_hash`
- `warnings`

Default:

- `schema_version = "risk_knowledge_answer.v1"`

The public `type` remains `risk_knowledge_answer`.

## 9. Trace Metadata

Each Risk QA run must record at least:

- `context_hash`
- `retrieval_snapshot_id`
- `selected_evidence_ids`
- `selected_chunk_ids`
- `blocked_context_sources`
- `grounding_status`
- `warning_codes`
- `citation_count`
- `evidence_count`

These fields must be written into orchestrator trace metadata without changing the current flow entrypoint.

## 10. Out Of Scope

PR-A does not include:

- M3 DAG work
- worker redesign
- SSE / WebSocket expansion
- Memory platform expansion
- Data Agent SQL HITL changes
- Data/Risk RAG mixing
- repo-wide rename to `risk_qa_*`
- dual public entrypoint rollout

## 11. Test Matrix

PR-A must cover:

- routing acceptance and non-stealing behavior
- context isolation positive and negative cases
- evidence normalization and selection
- sufficiency states
- citation gate blocking behavior
- facade compatibility
- orchestrator final artifact and trace metadata persistence
- Data Agent non-regression

## 12. Acceptance

PR-A is acceptable only if:

- existing `risk_knowledge_answer` callers remain compatible
- grounded answers require selected evidence and valid citations
- insufficient evidence skips answer generation
- blocked context sources are surfaced in artifacts
- orchestrator trace metadata includes the required QA fields
- Risk QA remains isolated from tool registry, Data Agent execution, and SQL HITL
