# M6B Policy-Gated Semantic Memory Retrieval Review

## 1. Scope

This closure reviews `M6B` as an acceptance-only pass. No new runtime behavior
was added during this step.

What M6B does:

- extends the shared `app/services/memory/*` runtime with policy-gated semantic
  retrieval
- keeps SQLite as the source of truth and treats FAISS/vector as candidate-only
- fuses semantic supplements behind feature flags while preserving legacy FTS as
  the default production path

What M6B does not do:

- does not open semantic context injection by default
- does not inject vector semantic supplement into Data Agent / SQL grounding
- does not add dashboard, rollout telemetry, or M6C observability
- does not mark overall `M6` as completed

## 2. Runtime Changes

The accepted M6B runtime surface consists of:

- `app/services/memory/vector_index_adapter.py`
- `app/services/memory/semantic_retrieval.py`
- `app/services/memory/fusion.py`
- `app/services/memory/hybrid_retrieval.py`
- `app/services/memory/retrieval.py`
- `app/services/memory/retrieval_adapter.py`
- `app/services/memory/context_builder.py`
- `app/services/orchestrator_agent/memory_context.py`

The architecture remains `Extend M4` rather than creating an
orchestrator-private retrieval runtime.

## 3. Guardrails

The closure audit re-confirmed the intended boundaries:

- vector candidates must relational-load from SQLite before use
- final context items must still pass shared memory policy and visibility checks
- `app/services/orchestrator_agent/memory_context.py` remains thin integration
  only
- `app/services/memory/vector_index_adapter.py` is the only temporary seam from
  the memory runtime into `app/services/orchestrator_agent/memory_vector/*`
- `MEMORY_VECTOR_CONTEXT_INJECTION_ENABLED=0` remains the default
- SQL/Data Agent paths remain excluded from semantic supplement in M6B
- prompt provenance stays minimal: `memory_id`, source type, authority,
  requested use, retrieval method, evidence status, and content only
- prompt-visible context does not expose `raw_distance`, policy internals, raw
  `metadata_json`, or vector sync internals

## 4. Eval / Release Gate Evidence

Acceptance closure reran the following checks on
`codex/m6b-policy-gated-semantic-memory`:

- `python -m compileall -q app data_acquisition_agent tests scripts`
  - passed
- `PYTHONPATH=. MODEL_MODE=mock pytest -q tests/orchestrator_agent/test_memory_semantic_retriever.py tests/orchestrator_agent/test_memory_retrieval_fusion.py tests/orchestrator_agent/test_memory_context_injection_semantic.py tests/eval/test_memory_semantic_retrieval_suite.py`
  - `8 passed, 1 warning`
- `PYTHONPATH=. MODEL_MODE=mock pytest -q tests/test_memory_retrieval_boundary.py tests/test_memory_context_builder.py tests/test_memory_type_isolation_contract.py`
  - `34 passed`
- `PYTHONPATH=. MODEL_MODE=mock pytest -q tests/orchestrator_agent`
  - `356 passed, 16 warnings`
- `python -m app.eval.runner --suite memory_governance`
  - passed
- `python -m app.eval.runner --suite memory_semantic_retrieval`
  - passed
- `python -m app.eval.runner --profile pr_acceptance`
  - passed
- `python -m app.eval.runner --profile production_release --strict`
  - passed
- `git diff --check`
  - passed in this closure step

The eval path remains hermetic and deterministic:

- temporary SQLite DB
- temporary vector index directory
- deterministic embedding provider
- explicit record seeding and sync
- no dependency on external embedding APIs
- no dependency on `outputs/memory/vector/default`

## 5. Known Limitations

- `MEMORY_VECTOR_CONTEXT_INJECTION_ENABLED` remains off by default
- no dashboard / rollout observability / M6C metrics have been added yet
- no Data Agent semantic memory supplement is enabled
- `vector_index_adapter.py` remains a temporary compatibility seam
- `M6` overall is not completed

## 6. Decision

`M6B` is implemented, release-gated, and accepted on the feature branch.

Accepted status wording for this branch is:

- `M6B accepted / ready to merge`
- `M6C not started`
- `M6 overall not completed`

`M6C Semantic Memory Rollout & Observability` may start after the M6B branch is
merged.
