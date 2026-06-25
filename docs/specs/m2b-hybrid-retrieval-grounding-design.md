# M2B Hybrid Retrieval & Grounding Design

## Goal

`M2B` is the follow-up stage after `M2A-RQ-FU7`. Its purpose is to improve the quality of Data Agent grounding before SQL generation by upgrading knowledge governance, retrieval evaluation, and eventually retrieval fusion.

This stage does not begin with vector search. It begins with inventory and evaluation so that later retrieval changes are measured against a stable baseline.

## Why M2B Starts With Inventory

The raw documents now stored under `docs/knowledge-base/` are not a safe runtime knowledge base:

- some files contain sensitive connection details and internal infrastructure references
- some files contain historical SQL with fixed dates, source filters, temporary tables, and unsafe literal-copy patterns
- some files contain valuable business logic, glossary definitions, schema hints, and data lineage clues

Because value and risk are mixed together, the correct first step is to govern the inputs before any chunking, embedding, or hybrid retrieval work.

## Stage Sequence

`M2B` proceeds in the following order:

1. `M2B-0 Knowledge Inventory & Retrieval Baseline`
2. `M2B-1 Structured Knowledge Extraction`
3. `M2B-2 Seed Import / Knowledge Store Update`
4. `M2B-3 Embedding Text Builder`
5. `M2B-4 Vector Index Prototype`
6. `M2B-5 Hybrid Retrieval Fusion`

## M2B-0 Scope

`M2B-0` delivers:

- legacy knowledge inventory
- knowledge asset taxonomy
- retrieval golden set
- baseline template artifacts
- a template-only baseline runner stub

`M2B-0` explicitly does not deliver:

- real retriever execution
- runtime retriever replacement
- embedding or vector index work
- changes to SQL HITL, approve/execute, or orchestrator bridge
- raw document prompt injection

## Runtime Boundary

During `M2B-0`:

- `docs/knowledge-base/` remains a local raw-input directory
- runtime truth remains the existing structured knowledge store and deterministic retriever
- no changes are allowed to `app/data_knowledge/retriever.py`
- no changes are allowed to `app/data_agent/service.py`
- no changes are allowed to SQL generation, review, repair, approve, or execute flow

## Outputs

The phase produces these commit-safe artifacts:

- inventory review report
- knowledge asset taxonomy
- retrieval golden set
- baseline template JSON
- baseline template review report

All runtime-eligible knowledge must be extracted later as sanitized structured assets, not reused as raw markdown.
